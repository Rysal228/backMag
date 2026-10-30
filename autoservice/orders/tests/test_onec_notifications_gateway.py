"""Service authentication and response validation without a live 1C instance."""
from unittest.mock import Mock, patch

import requests
from django.test import SimpleTestCase, override_settings

from integrations.services.onec_notifications import OneCNotificationError, OneCNotificationsClient


ORDER = "4a1c96c9-61cc-4b9f-a215-8f85c61fcb07"
CAR = "0ce3b354-64b7-4601-b593-fcfb23de5592"
OWNER = "1b738f3d-d8bd-4873-9fc1-6be7a87b9043"
KEY = "test-notification-key-" + "A" * 43


def record():
    return {"id": ORDER, "car": CAR, "ownerId": OWNER, "orderNumber": "00000125",
            "carName": "Toyota Camry", "status": {"code": "in_progress", "name": "В работе"},
            "workStatus": {"code": "execution", "name": "Ремонт"}}


def response(body, status=200):
    return Mock(status_code=status, json=Mock(return_value=body))


@override_settings(ONEC_NOTIFICATIONS_SERVICE_KEY=KEY)
@patch.dict("os.environ", {"ONEC_BASE_URL": "http://host.docker.internal:8081",
                          "ONEC_ORDERS_PATH": "/ServiceCar/hs/api"})
class NotificationGatewayTests(SimpleTestCase):
    @patch("integrations.services.onec_notifications.requests.get")
    @override_settings(MAX_ORDER_NOTIFICATIONS_MANAGER_ID="not-a-user-uuid")
    def test_service_header_without_actor_or_application_login(self, get):
        get.return_value = response([record()])
        self.assertEqual(OneCNotificationsClient().list_orders()[0]["ownerId"], OWNER)
        args, kwargs = get.call_args
        self.assertEqual(args[0], "http://host.docker.internal:8081/ServiceCar/hs/api/notifications/orders")
        self.assertEqual(kwargs["headers"]["X-ServiceCar-Notifications-Key"], KEY)
        self.assertNotIn("params", kwargs)
        self.assertNotIn("auth", kwargs)
        self.assertFalse(kwargs["allow_redirects"])

    @patch("integrations.services.onec_notifications.requests.get")
    def test_missing_invalid_key_fails_before_network(self, get):
        for key in ("", "short", "A" * 129, "A" * 32 + "\n", "я" * 64):
            with self.subTest(key_length=len(key)), override_settings(ONEC_NOTIFICATIONS_SERVICE_KEY=key):
                with self.assertRaises(OneCNotificationError):
                    OneCNotificationsClient()
        get.assert_not_called()

    def test_public_plain_http_and_embedded_credentials_are_rejected(self):
        for base in ("http://example.test", "https://user:secret@example.test",
                     "https://example.test?key=secret", "https://example.test/path"):
            with self.subTest(base=base), patch.dict("os.environ", {"ONEC_BASE_URL": base}):
                with self.assertRaises(OneCNotificationError):
                    OneCNotificationsClient()

    def test_custom_https_server_is_supported(self):
        with patch.dict("os.environ", {"ONEC_BASE_URL": "https://onec.example.test"}):
            self.assertTrue(OneCNotificationsClient().base.startswith("https://onec.example.test/"))

    @patch("integrations.services.onec_notifications.requests.get")
    def test_rejected_key_and_redirect_do_not_fall_back_or_leak_body(self, get):
        for status in (401, 403, 301, 302, 500):
            get.reset_mock()
            get.return_value = response({"message": KEY}, status)
            with self.subTest(status=status), self.assertRaises(OneCNotificationError) as ctx:
                OneCNotificationsClient().list_orders()
            self.assertNotIn(KEY, str(ctx.exception))
            get.assert_called_once()

    @patch("integrations.services.onec_notifications.requests.get")
    def test_timeout_does_not_leak_request_details(self, get):
        get.side_effect = requests.Timeout(KEY)
        with self.assertRaises(OneCNotificationError) as ctx:
            OneCNotificationsClient().list_orders()
        self.assertNotIn(KEY, str(ctx.exception))

    @patch("integrations.services.onec_notifications.requests.get")
    def test_complete_feed_is_validated_and_duplicate_ids_are_rejected(self, get):
        invalid = record(); invalid["car"] = "not-uuid"
        for body in ({"results": []}, [record(), invalid], [record(), record()]):
            get.return_value = response(body)
            with self.subTest(body_type=type(body).__name__), self.assertRaises(OneCNotificationError):
                OneCNotificationsClient().list_orders()

    @patch("integrations.services.onec_notifications.requests.get")
    def test_missing_owner_is_explicitly_unmapped(self, get):
        row = record(); row["ownerId"] = None
        get.return_value = response([row])
        self.assertIsNone(OneCNotificationsClient().list_orders()[0]["ownerId"])

    @patch("integrations.services.onec_notifications.requests.get")
    def test_html_response_is_safe_error(self, get):
        get.return_value = response(None)
        get.return_value.json.side_effect = ValueError(KEY)
        with self.assertRaises(OneCNotificationError) as ctx:
            OneCNotificationsClient().list_orders()
        self.assertNotIn(KEY, str(ctx.exception))

    @patch("integrations.services.onec_notifications.requests.get")
    def test_recipient_rechecks_order_and_uses_header(self, get):
        row = {"id": ORDER, "car": CAR, "ownerId": OWNER, "eligible": True,
               "messengerUserId": "77335511"}
        get.return_value = response(row)
        self.assertEqual(OneCNotificationsClient().recipient(ORDER), row)
        self.assertTrue(get.call_args.args[0].endswith(f"/{ORDER}/recipient"))
        row["id"] = CAR
        with self.assertRaises(OneCNotificationError):
            OneCNotificationsClient().recipient(ORDER)

    @patch("integrations.services.onec_notifications.requests.get")
    def test_removed_order_is_not_deliverable(self, get):
        get.return_value = response({}, 404)
        self.assertIsNone(OneCNotificationsClient().recipient(ORDER))

    @patch("integrations.services.onec_notifications.requests.get")
    def test_eligible_requires_boolean_valid_owner_and_numeric_max_id(self, get):
        for changes in ({"eligible": "true"}, {"ownerId": None}, {"messengerUserId": "abc"}):
            row = {"id": ORDER, "car": CAR, "ownerId": OWNER, "eligible": True,
                   "messengerUserId": "77335511", **changes}
            get.return_value = response(row)
            with self.subTest(changes=changes), self.assertRaises(OneCNotificationError):
                OneCNotificationsClient().recipient(ORDER)
