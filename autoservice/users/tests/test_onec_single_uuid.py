"""Regression tests for the native 1C UUID protocol.

Old test suites that assumed separate local/external UUIDs are being retired.
"""
from uuid import UUID
from unittest.mock import Mock, patch

from django.test import TestCase, SimpleTestCase

from integrations.services.onec_max import OneCMaxClient
from integrations.services.onec_users import OneCUsersClient
from users.auth.services import AuthService
from users.models import CustomUser

NATIVE = "d2b65827-0e38-48b8-a27e-4aef3ce3c135"
PHONE = "79135572795"
MAX_ID = "123456789"


def profile(*, roles=None, messenger="", password=True):
    return {
        "onecId": NATIVE,
        "phone": PHONE,
        "firstName": "Ирина",
        "lastName": "Тестовая",
        "patronymic": "",
        "birthday": None,
        "roles": roles if roles is not None else ["user"],
        "messengerUserId": messenger,
        "isActive": True,
        "hasPassword": password,
    }


class NativeUUIDClientTests(SimpleTestCase):
    @patch("integrations.services.onec_users.requests.request")
    def test_registration_payload_contains_only_native_id_on_response(self, request):
        response = Mock(status_code=201, ok=True)
        response.json.return_value = {"user": profile()}
        request.return_value = response

        user_id = OneCUsersClient().create_user_with_password(
            phone=PHONE, password="example-password-123",
            first_name="Ирина", last_name="Тестовая",
        )
        self.assertEqual(user_id, NATIVE)
        payload = request.call_args.kwargs["json"]
        self.assertNotIn("externalId", payload)
        self.assertEqual(payload["phone"], PHONE)

    @patch.object(OneCMaxClient, "_post")
    def test_max_resolve_does_not_require_local_uuid(self, post):
        post.return_value = {
            "status": "ok", "user": profile(messenger=MAX_ID),
        }
        current = OneCMaxClient().resolve(
            messenger_user_id=MAX_ID, phone=PHONE,
        )
        self.assertEqual(current["onecId"], NATIVE)
        payload = post.call_args.args[1]
        self.assertEqual(payload["phone"], PHONE)
        self.assertNotIn("externalId", payload)


class NativeIdentityLoginTests(TestCase):
    @patch("users.auth.services.OneCUsersClient")
    @patch("users.auth.services.OneCPasswordAuthClient")
    def test_login_of_1c_only_user_creates_native_uuid_mirror(self, password_client, profiles):
        self.assertEqual(CustomUser.objects.count(), 0)
        password_client.return_value.verify_password.return_value = {
            "onecId": NATIVE, "phone": PHONE, "roles": ["user"],
        }
        profiles.return_value.get_user_by_onec_id.return_value = profile()

        data = AuthService.login(phone="+" + PHONE, password="example")
        self.assertIn("accessToken", data)
        user = CustomUser.objects.get(phone=PHONE)
        self.assertEqual(user.pk, UUID(NATIVE))
        self.assertEqual(user.onec_id, UUID(NATIVE))
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.get_roles(), ["user"])

    @patch("users.auth.services.OneCUsersClient")
    def test_registration_uses_uuid_created_by_1c(self, client):
        client.return_value.create_user_with_password.return_value = NATIVE
        client.return_value.get_user_by_onec_id.return_value = profile()

        data = AuthService.register(
            phone="+" + PHONE, password="example-password-123",
            first_name="Ирина", last_name="Тестовая",
        )
        self.assertIn("accessToken", data)
        self.assertEqual(CustomUser.objects.get(phone=PHONE).pk, UUID(NATIVE))
        self.assertNotIn(
            "external_id",
            client.return_value.create_user_with_password.call_args.kwargs,
        )
