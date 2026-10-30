"""Isolated notification tests: never contact 1C or MAX."""
from unittest.mock import patch
from uuid import UUID

from django.test import TestCase, override_settings
from django.utils import timezone
from django.core.management import call_command
from django.core.management.base import CommandError

from integrations.services.onec_notifications import OneCNotificationError

from orders.models import OrderNotificationDelivery, OrderNotificationSnapshot
from orders.services.max_notifications import (
    build_message, poll_order_statuses, send_pending_notifications,
)


ORDER = "4a1c96c9-61cc-4b9f-a215-8f85c61fcb07"
CAR = "0ce3b354-64b7-4601-b593-fcfb23de5592"
OWNER = "1b738f3d-d8bd-4873-9fc1-6be7a87b9043"
OTHER = "718928b8-d44c-4d8f-ac9c-c6e9aeec6454"


def record(status="under_review", work="manager_review"):
    return {
        "id": ORDER, "car": CAR, "ownerId": OWNER, "orderNumber": "00000125",
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


def recipient(owner=OWNER, eligible=True):
    return {"id": ORDER, "car": CAR, "ownerId": owner, "eligible": eligible,
            "messengerUserId": "77335511" if eligible else ""}


@override_settings(
    ONEC_NOTIFICATIONS_SERVICE_KEY="test-key-" + "a" * 48,
    MAX_ORDER_NOTIFICATIONS_PUBLIC_URL="https://service.example.test",
)
class MaxOrderNotificationTests(TestCase):

    @patch("orders.services.max_notifications.OneCNotificationsClient")
    def test_initial_scan_is_baseline_and_second_change_queues_once(self, client):
        client.return_value.list_orders.return_value = [record()]
        self.assertEqual(poll_order_statuses()["baseline"], 1)
        self.assertFalse(OrderNotificationDelivery.objects.exists())
        client.return_value.list_orders.return_value = [record("in_progress", "execution")]
        self.assertEqual(poll_order_statuses()["queued"], 1)
        self.assertEqual(poll_order_statuses()["queued"], 0)
        entry = OrderNotificationDelivery.objects.get()
        self.assertTrue(entry.order_changed)
        self.assertTrue(entry.work_changed)
        self.assertEqual(entry.revision, 1)
        self.assertEqual(entry.owner_id, UUID(OWNER))
        client.return_value.list_orders.assert_called_with()

    @patch("orders.services.max_notifications.OneCNotificationsClient")
    def test_work_status_only_change_is_not_lost(self, client):
        client.return_value.list_orders.return_value = [record()]
        poll_order_statuses()
        client.return_value.list_orders.return_value = [record(work="execution")]
        self.assertEqual(poll_order_statuses()["queued"], 1)
        entry = OrderNotificationDelivery.objects.get()
        self.assertFalse(entry.order_changed)
        self.assertTrue(entry.work_changed)
        self.assertIn("Статус работ:", build_message(entry))
        self.assertIn(f"/appointments/{ORDER}", build_message(entry))
        self.assertNotIn("7999", build_message(entry))

    @patch("orders.services.max_notifications.OneCNotificationsClient")
    def test_owner_mismatch_does_not_route_transition_to_new_customer(self, client):
        client.return_value.list_orders.return_value = [record()]
        poll_order_statuses()
        client.return_value.list_orders.return_value = [record("in_progress")]
        client.return_value.list_orders.return_value[0]["ownerId"] = OTHER
        self.assertEqual(poll_order_statuses()["queued"], 0)
        self.assertEqual(OrderNotificationSnapshot.objects.get().owner_id, UUID(OTHER))

    @patch("orders.services.max_notifications.MaxBotClient")
    @patch("orders.services.max_notifications.OneCNotificationsClient")
    def test_send_uses_max_id_from_verified_onec_owner(self, client, bot):
        client.return_value.recipient.return_value = recipient()
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
    @patch("orders.services.max_notifications.OneCNotificationsClient")
    def test_unlinked_user_is_skipped_not_notified(self, client, bot):
        client.return_value.recipient.return_value = recipient(eligible=False)
        OrderNotificationDelivery.objects.create(
            order_id=ORDER, car_id=CAR, owner_id=OWNER, revision=1,
            order_number="00000125", car_name="Toyota Camry",
            order_code="in_progress", order_changed=True,
        )
        self.assertEqual(send_pending_notifications()["skipped"], 1)
        self.assertEqual(OrderNotificationDelivery.objects.get().state, "skipped")
        bot.assert_not_called()

    @patch("orders.services.max_notifications.MaxBotClient")
    @patch("orders.services.max_notifications.OneCNotificationsClient")
    def test_send_failure_is_queued_for_retry(self, client, bot):
        client.return_value.recipient.return_value = recipient()
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
    @patch("orders.services.max_notifications.OneCNotificationsClient")
    def test_send_fails_closed_if_owner_changed(self, client, bot):
        client.return_value.recipient.return_value = recipient(owner=OTHER)
        OrderNotificationDelivery.objects.create(
            order_id=ORDER, car_id=CAR, owner_id=OWNER, revision=1,
            order_number="00000125", car_name="Toyota Camry",
            order_code="completed", order_changed=True,
        )
        self.assertEqual(send_pending_notifications()["skipped"], 1)
        bot.assert_not_called()

    @patch("orders.services.max_notifications.OneCNotificationsClient")
    def test_existing_pr74_snapshot_continues_revision_without_new_baseline(self, client):
        OrderNotificationSnapshot.objects.create(
            order_id=ORDER, car_id=CAR, owner_id=OWNER,
            order_code="under_review", work_code="manager_review", revision=4,
        )
        client.return_value.list_orders.return_value = [record("in_progress")]
        self.assertEqual(poll_order_statuses(), {"baseline": 0, "queued": 1, "unmapped": 0})
        self.assertEqual(OrderNotificationDelivery.objects.get().revision, 5)

    @patch("orders.services.max_notifications.OneCNotificationsClient")
    def test_feed_failure_does_not_reset_existing_snapshot(self, client):
        OrderNotificationSnapshot.objects.create(
            order_id=ORDER, car_id=CAR, owner_id=OWNER,
            order_code="under_review", work_code="manager_review", revision=4,
        )
        client.return_value.list_orders.side_effect = OneCNotificationError("unavailable")
        with self.assertRaises(OneCNotificationError):
            poll_order_statuses()
        self.assertEqual(OrderNotificationSnapshot.objects.get().revision, 4)
        self.assertFalse(OrderNotificationDelivery.objects.exists())

    @patch("orders.services.max_notifications.MaxBotClient")
    @patch("orders.services.max_notifications.OneCNotificationsClient")
    def test_pending_pr74_notification_for_deleted_order_is_skipped(self, client, bot):
        client.return_value.recipient.return_value = None
        OrderNotificationDelivery.objects.create(
            order_id=ORDER, car_id=CAR, owner_id=OWNER, revision=4,
            order_number="00000125", car_name="Toyota Camry", order_code="in_progress",
            order_changed=True,
        )
        self.assertEqual(send_pending_notifications()["skipped"], 1)
        bot.assert_not_called()

    @override_settings(MAX_ORDER_NOTIFICATIONS_ENABLED=True, ONEC_NOTIFICATIONS_SERVICE_KEY="")
    @patch("orders.services.max_notifications.OneCNotificationsClient")
    def test_command_rejects_missing_key_before_poll_or_send(self, client):
        with self.assertRaises(CommandError):
            call_command("poll_order_notifications")
        client.assert_not_called()
