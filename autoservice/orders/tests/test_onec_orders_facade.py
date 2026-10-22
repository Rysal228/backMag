"""Offline facade tests: no Order ORM, only one 1C gateway for data."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import SimpleTestCase, TestCase
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied, ValidationError

from orders.views import (
    OrderViewSet, WorkTypeViewSet, AppointmentAvailabilityView,
    OrderStatisticsView, OrderStatisticsPeriodsView,
    _order_payload,
)
from orders.models import StatisticsPeriodOption
from chats.models import ChatRoom
from chats.permissions import can_access_room_for


ACTOR = UUID("8996ef81-9116-4d75-a3de-2fa8a5bc6b10")
CAR = "3bc5c300-d1e0-471e-8f4c-cc1f8610db8c"
ORDER = "21afe47c-5403-4805-9442-b1d10e84f97d"
WORK = "8449407b-315d-4fa9-b058-2727c43a1b78"
STATUS = "575274d0-f291-4826-8dc5-97cfa32d9ab1"


def actor(data=None, role="user", params=None):
    return SimpleNamespace(
        user=SimpleNamespace(id=ACTOR, pk=ACTOR),
        active_role=role,
        data=data or {},
        query_params=params or {},
    )


class OrdersFacadeTests(SimpleTestCase):
    @patch("orders.views.OneCOrdersClient")
    def test_order_detail_is_fetched_from_1c(self, gateway):
        gateway.return_value.get.return_value = {"id": ORDER, "orderNumber": "1"}
        result = OrderViewSet().retrieve(actor(), pk=ORDER)
        self.assertEqual(result.data["id"], ORDER)
        gateway.return_value.get.assert_called_once_with(ORDER, ACTOR, "user")

    @patch("orders.views.OneCOrdersClient")
    def test_create_without_works(self, gateway):
        gateway.return_value.create.return_value = {"id": ORDER}
        payload = {"car": CAR, "works": [], "description": "Диагностика"}
        result = OrderViewSet().create(actor(payload))
        self.assertEqual(result.status_code, 201)
        gateway.return_value.create.assert_called_once_with(payload, ACTOR, "user")

    @patch("orders.views.OneCOrdersClient")
    def test_patch_does_not_touch_postgresql(self, gateway):
        gateway.return_value.patch.return_value = {"id": ORDER}
        result = OrderViewSet().partial_update(
            actor({"description": "Исправлено"}, role="admin"), pk=ORDER
        )
        self.assertEqual(result.data["id"], ORDER)
        gateway.return_value.patch.assert_called_once_with(
            ORDER, {"description": "Исправлено"}, ACTOR, "admin"
        )

    @patch("orders.views.OneCOrdersClient")
    def test_catalog_from_1c(self, gateway):
        gateway.return_value.work_types.return_value = [{"id": WORK, "name": "Осмотр"}]
        result = WorkTypeViewSet().list(actor())
        self.assertEqual(result.data[0]["id"], WORK)

    @patch("orders.views.OneCOrdersClient")
    def test_work_status_direct_assignment(self, gateway):
        gateway.return_value.transition_work_status.return_value = {"id": ORDER}
        result = OrderViewSet().transition_work_status(
            actor({"statusId": STATUS}, role="admin"), pk=ORDER
        )
        self.assertEqual(result.data["id"], ORDER)
        gateway.return_value.transition_work_status.assert_called_once_with(
            ORDER, STATUS, ACTOR, "admin"
        )

    @patch("orders.views.OneCOrdersClient")
    def test_availability_from_1c(self, gateway):
        gateway.return_value.availability.return_value = {"availableSlots": ["09:00"]}
        result = AppointmentAvailabilityView().get(actor(params={"date": "2026-10-23"}))
        self.assertEqual(result.data["availableSlots"], ["09:00"])

    @patch("orders.views.OneCOrdersClient")
    @patch("orders.views.validate_filter_permissions")
    def test_list_checks_django_filter_rights_then_calls_1c(self, validator, gateway):
        gateway.return_value.list_orders.return_value = []
        result = OrderViewSet().list(actor(params={"status": STATUS}))
        validator.assert_called_once()
        gateway.return_value.list_orders.assert_called_once_with(
            ACTOR, "user", filters={"status": STATUS}
        )
        self.assertEqual(result.data["results"], [])

    def test_free_text_works_rejected(self):
        with self.assertRaises(ValidationError):
            _order_payload(actor({"car": CAR, "works": [{"name": "Моя"}]}))

    def test_unknown_fields_rejected(self):
        with self.assertRaises(ValidationError):
            _order_payload(actor({"car": CAR, "customerId": str(ACTOR)}))

    def test_delete_explicitly_forbidden(self):
        with self.assertRaises(MethodNotAllowed):
            OrderViewSet().destroy(actor(), pk=ORDER)

    @patch("orders.views._statistics_periods", return_value=[
        {"days": 7, "is_default": False},
        {"days": 30, "is_default": True},
        {"days": 90, "is_default": False},
    ])
    @patch("orders.views.timezone.localdate", return_value=date(2026, 10, 22))
    @patch("orders.views.OneCOrdersClient")
    def test_statistics_gateway_receives_bounded_period(self, gateway, today, periods):
        gateway.return_value.statistics.return_value = {"summary": {"orders": 0}}
        result = OrderStatisticsView().get(actor(role="admin", params={"days": "30"}))
        self.assertEqual(result.data["summary"]["orders"], 0)
        gateway.return_value.statistics.assert_called_once_with(
            ACTOR, "admin", date(2026, 9, 23), date(2026, 10, 22)
        )

    @patch("orders.views.OneCOrdersClient")
    def test_statistics_rejects_non_manager(self, gateway):
        with self.assertRaises(PermissionDenied):
            OrderStatisticsView().get(actor(role="mechanic", params={"days": "30"}))
        gateway.assert_not_called()

    @patch("orders.views._statistics_periods", return_value=[
        {"days": 7, "is_default": False},
        {"days": 30, "is_default": True},
        {"days": 90, "is_default": False},
    ])
    def test_statistics_rejects_oversized_period(self, periods):
        with self.assertRaises(ValidationError):
            OrderStatisticsView().get(actor(role="admin", params={"days": "365"}))

    @patch("orders.views._statistics_periods", return_value=[
        {"days": 14, "is_default": True},
        {"days": 60, "is_default": False},
    ])
    def test_statistics_periods_api_returns_django_configuration(self, periods):
        result = OrderStatisticsPeriodsView().get(actor(role="admin"))
        self.assertEqual(result.data, {
            "periods": [{"days": 14}, {"days": 60}],
            "defaultDays": 14,
        })

    @patch("orders.views._statistics_periods")
    def test_statistics_periods_api_rejects_non_manager(self, periods):
        with self.assertRaises(PermissionDenied):
            OrderStatisticsPeriodsView().get(actor(role="user"))
        periods.assert_not_called()

    @patch("orders.views._statistics_periods", return_value=[
        {"days": 14, "is_default": True},
    ])
    @patch("orders.views.timezone.localdate", return_value=date(2026, 10, 22))
    @patch("orders.views.OneCOrdersClient")
    def test_statistics_custom_period_and_default(self, gateway, today, periods):
        gateway.return_value.statistics.return_value = {"summary": {"orders": 5}}
        response = OrderStatisticsView().get(actor(role="admin"))
        self.assertEqual(response.data["summary"]["orders"], 5)
        gateway.return_value.statistics.assert_called_once_with(
            ACTOR, "admin", date(2026, 10, 9), date(2026, 10, 22)
        )

    @patch("orders.views._statistics_periods", return_value=[])
    def test_statistics_no_configured_periods(self, periods):
        self.assertIsNone(OrderStatisticsPeriodsView().get(actor(role="admin")).data["defaultDays"])
        with self.assertRaises(ValidationError):
            OrderStatisticsView().get(actor(role="admin", params={"days": "7"}))




class ChatGatewayPermissionsTests(SimpleTestCase):
    @patch("chats.permissions.OneCOrdersClient")
    def test_mechanic_chat_needs_actual_order_assignment(self, gateway):
        gateway.return_value.get.return_value = {"id": ORDER, "mechanics": []}
        room = ChatRoom(order_id=UUID(ORDER), type=ChatRoom.Type.MANAGER_MECHANIC,
                        mechanic_id=ACTOR)
        user = SimpleNamespace(id=ACTOR, pk=ACTOR)
        self.assertFalse(can_access_room_for(room, user, "mechanic"))
        gateway.return_value.get.return_value = {
            "id": ORDER, "mechanics": [str(ACTOR)],
        }
        self.assertTrue(can_access_room_for(room, user, "mechanic"))

    @patch("chats.permissions.OneCOrdersClient")
    def test_user_order_chat_requires_1c_authorization(self, gateway):
        from integrations.services.onec_orders import OneCOrderError
        gateway.return_value.get.side_effect = OneCOrderError("order_not_found", "Нет", 404)
        room = ChatRoom(order_id=UUID(ORDER), type=ChatRoom.Type.CUSTOMER_MANAGER)
        self.assertFalse(can_access_room_for(room, SimpleNamespace(pk=ACTOR), "user"))


class StatisticsPeriodOptionModelTests(TestCase):
    def setUp(self):
        StatisticsPeriodOption.objects.all().delete()

    def test_enabled_choices_are_ordered_and_default_is_configured(self):
        from orders.views import _statistics_periods, _statistics_default

        StatisticsPeriodOption.objects.create(days=60, enabled=True)
        StatisticsPeriodOption.objects.create(days=14, enabled=True, is_default=True)
        StatisticsPeriodOption.objects.create(days=90, enabled=False)

        periods = _statistics_periods()
        self.assertEqual([item["days"] for item in periods], [14, 60])
        self.assertEqual(_statistics_default(periods), 14)

    def test_invalid_duration_and_disabled_default_rejected(self):
        long_period = StatisticsPeriodOption(days=91)
        with self.assertRaises(DjangoValidationError):
            long_period.full_clean()

        invalid_default = StatisticsPeriodOption(
            days=14, enabled=False, is_default=True,
        )
        with self.assertRaises(DjangoValidationError):
            invalid_default.full_clean()

    def test_default_falls_back_to_first_enabled_period(self):
        from orders.views import _statistics_periods, _statistics_default

        StatisticsPeriodOption.objects.create(days=14, enabled=True)
        StatisticsPeriodOption.objects.create(days=60, enabled=True)
        self.assertEqual(_statistics_default(_statistics_periods()), 14)
