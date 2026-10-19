"""Regression tests for the native 1C UUID protocol.

Old test suites that assumed separate local/external UUIDs are being retired.
"""
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from integrations.services.onec_max import OneCMaxClient
from integrations.services.onec_users import OneCUsersClient

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

