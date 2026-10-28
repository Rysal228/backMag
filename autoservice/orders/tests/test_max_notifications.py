"""Isolated notification tests: never contact 1C or MAX."""
from unittest.mock import patch
from uuid import UUID

from django.test import TestCase, override_settings
from django.utils import timezone

from orders.models import OrderNotificationDelivery, OrderNotificationSnapshot
from orders.services.max_notifications import (
    build_message, poll_order_statuses, send_pending_notifications,
)


MANAGER = "2100994a-b56e-48b6-97a8-a0d173ff65de"
ORDER = "4a1c96c9-61cc-4b9f-a215-8f85c61fcb07"
CAR = "0ce3b354-64b7-4601-b593-fcfb23de5592"
OWNER = "1b738f3d-d8bd-4873-9fc1-6be7a87b9043"
OTHER = "718928b8-d44c-4d8f-ac9c-c6e9aeec6454"


def record(status="under_review", work="manager_review"):
    return {
        "id": ORDER, "car": CAR, "orderNumber": "00000125",
        "carName": "Toyota Camry",
        "status": {"code": status, "name": {
            "under_review": "На рассмотрении", "in_progress": "В работе",
            "completed": "Завершён",
        }.get(status, status)},
        "workStatus": {"code": work, "name": {
            "manager_review": "Рассмотрение менеджером",
            "execution": "Выполняются работы",
            "owner_visit": "Владелец должен явиться в сервис",
        }.get(work, work)},
    }


def vehicle(owner=OWNER):
    return {"id": CAR, "ownerId": owner}


@override_settings(
    MAX_ORDER_NOTIFICATIONS_MANAGER_ID=MANAGER,
    MAX_ORDER_NOTIFICATIONS_PUBLIC_URL="https://service.example.test",
)
class MaxOrderNotificationTests(TestCase):

    @patch("orders.services.max_notifications.OneCCarsClient")
    @patch("orders.services.max_notifications.OneCOrdersClient")
    def test_initial_scan_is_baseline_and_second_change_queues_once(self, orders, cars):
        orders.return_value.list_orders.return_value = [record()]
        cars.return_value.list_cars.return_value = [vehicle()]
        self.assertEqual(poll_order_statuses()["baseline"], 1)
        self.assertFalse(OrderNotificationDelivery.objects.exists())
        orders.return_value.list_orders.return_value = [record("in_progress", "execution")]
        self.assertEqual(poll_order_statuses()["queued"], 1)
        self.assertEqual(poll_order_statuses()["queued"], 0)
        entry = OrderNotificationDelivery.objects.get()
        self.assertTrue(entry.order_changed)
        self.assertTrue(entry.work_changed)
        self.assertEqual(entry.revision, 1)
        self.assertEqual(entry.owner_id, UUID(OWNER))
        orders.return_value.list_orders.assert_called_with(MANAGER, "admin")

    @patch("orders.services.max_notifications.OneCCarsClient")
    @patch("orders.services.max_notifications.OneCOrdersClient")
    def test_work_status_only_change_is_not_lost(self, orders, cars):
        orders.return_value.list_orders.return_value = [record()]
        cars.return_value.list_cars.return_value = [vehicle()]
        poll_order_statuses()
        orders.return_value.list_orders.return_value = [record(work="execution")]
        self.assertEqual(poll_order_statuses()["queued"], 1)
        entry = OrderNotificationDelivery.objects.get()
        self.assertFalse(entry.order_changed)
        self.assertTrue(entry.work_changed)
        self.assertIn("Статус работ:", build_message(entry))
        self.assertIn(f"/appointments/{ORDER}", build_message(entry))
        self.assertNotIn("7999", build_message(entry))

    @patch("orders.services.max_notifications.OneCCarsClient")
    @patch("orders.services.max_notifications.OneCOrdersClient")
    def test_owner_mismatch_does_not_route_transition_to_new_customer(self, orders, cars):
        orders.return_value.list_orders.return_value = [record()]
        cars.return_value.list_cars.return_value = [vehicle()]
        poll_order_statuses()
        orders.return_value.list_orders.return_value = [record("in_progress")]
        cars.return_value.list_cars.return_value = [vehicle(OTHER)]
        self.assertEqual(poll_order_statuses()["queued"], 0)
        self.assertEqual(OrderNotificationSnapshot.objects.get().owner_id, UUID(OTHER))

    @patch("orders.services.max_notifications.MaxBotClient")
    @patch("orders.services.max_notifications.OneCUsersClient")
    @patch("orders.services.max_notifications.OneCCarsClient")
    def test_send_uses_max_id_from_verified_onec_owner(self, cars, users, bot):
        cars.return_value.get.return_value = vehicle()
        users.return_value.get_user_by_onec_id.return_value = {
            "messengerUserId": "77335511", "isActive": True,
        }
        OrderNotificationDelivery.objects.create(
            order_id=ORDER, car_id=CAR, owner_id=OWNER, revision=1,
            order_number="00000125", car_name="Toyota Camry",
            order_code="completed", work_code="owner_visit",
            order_label="Завершён", work_label="Владелец должен явиться в сервис",
            order_changed=True, work_changed=True,
        )
        self.assertEqual(send_pending_notifications()["sent"], 1)
        self.assertEqual(send_pending_notifications()["sent"], 0)
        bot.return_value.send_message_to_user.assert_called_once()
        self.assertEqual(bot.return_value.send_message_to_user.call_args.kwargs["user_id"], "77335511")
        self.assertEqual(OrderNotificationDelivery.objects.get().state, "sent")

    @patch("orders.services.max_notifications.MaxBotClient")
    @patch("orders.services.max_notifications.OneCUsersClient")
    @patch("orders.services.max_notifications.OneCCarsClient")
    def test_unlinked_user_is_skipped_not_notified(self, cars, users, bot):
        cars.return_value.get.return_value = vehicle()
        users.return_value.get_user_by_onec_id.return_value = {
            "messengerUserId": "", "isActive": True,
        }
        OrderNotificationDelivery.objects.create(
            order_id=ORDER, car_id=CAR, owner_id=OWNER, revision=1,
            order_number="00000125", car_name="Toyota Camry",
            order_code="in_progress", order_changed=True,
        )
        self.assertEqual(send_pending_notifications()["skipped"], 1)
        self.assertEqual(OrderNotificationDelivery.objects.get().state, "skipped")
        bot.assert_not_called()

    @patch("orders.services.max_notifications.MaxBotClient")
    @patch("orders.services.max_notifications.OneCUsersClient")
    @patch("orders.services.max_notifications.OneCCarsClient")
    def test_send_failure_is_queued_for_retry(self, cars, users, bot):
        cars.return_value.get.return_value = vehicle()
        users.return_value.get_user_by_onec_id.return_value = {
            "messengerUserId": "77335511", "isActive": True,
        }
        bot.return_value.send_message_to_user.side_effect = RuntimeError("MAX unavailable")
        OrderNotificationDelivery.objects.create(
            order_id=ORDER, car_id=CAR, owner_id=OWNER, revision=1,
            order_number="00000125", car_name="Toyota Camry",
            order_code="in_progress", order_changed=True,
        )
        before = timezone.now()
        self.assertEqual(send_pending_notifications()["retry"], 1)
        entry = OrderNotificationDelivery.objects.get()
        self.assertEqual(entry.state, "pending")
        self.assertEqual(entry.attempts, 1)
        self.assertGreater(entry.next_attempt_at, before)
        self.assertEqual(send_pending_notifications()["retry"], 0)

    @patch("orders.services.max_notifications.MaxBotClient")
    @patch("orders.services.max_notifications.OneCCarsClient")
    def test_send_fails_closed_if_owner_changed(self, cars, bot):
        cars.return_value.get.return_value = vehicle(OTHER)
        OrderNotificationDelivery.objects.create(
            order_id=ORDER, car_id=CAR, owner_id=OWNER, revision=1,
            order_number="00000125", car_name="Toyota Camry",
            order_code="completed", order_changed=True,
        )
        self.assertEqual(send_pending_notifications()["skipped"], 1)
        bot.assert_not_called()
