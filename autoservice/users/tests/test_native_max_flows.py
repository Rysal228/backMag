"""MAX login and code authentication cannot depend on a Django user row."""
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import AccessToken

from integrations.services.onec_max import OneCMaxClient, OneCMaxError
from users.auth.max.services import MaxAuthService

ONEC_ID = "d2b65827-0e38-48b8-a27e-4aef3ce3c135"
PHONE = "79135572795"
MAX_ID = "918273645"


def profile():
    return {
        "onecId": ONEC_ID, "phone": PHONE, "messengerUserId": MAX_ID,
        "roles": ["user"], "isActive": True,
        "firstName": "Ирина", "lastName": "Тестовая",
    }


class NativeMaxFlows(SimpleTestCase):
    @patch("users.auth.max.services.OneCMaxClient")
    @patch("users.auth.max.services.MaxInitDataValidator.validate")
    def test_existing_max_user_logs_in_without_django_row(self, validator, client):
        validator.return_value = SimpleNamespace(
            user_id=int(MAX_ID), first_name="Ирина", last_name="Тестовая",
        )
        client.return_value.resolve.return_value = profile()
        result = MaxAuthService.authenticate(init_data="signed-value")
        claims = AccessToken(result["accessToken"])
        self.assertEqual(claims["user_id"], ONEC_ID)
        self.assertEqual(claims["auth_method"], "max")
        self.assertEqual(claims["messenger_user_id"], MAX_ID)

    @patch("users.auth.max.services.OneCMaxClient")
    @patch("users.auth.max.services.MaxInitDataValidator.validate")
    def test_missing_max_binding_requests_verified_phone(self, validator, client):
        validator.return_value = SimpleNamespace(user_id=int(MAX_ID))
        client.return_value.resolve.return_value = None
        result = MaxAuthService.authenticate(init_data="signed-value")
        self.assertEqual(result, {"status": "contact_required"})

    @patch("users.auth.max.services.OneCMaxClient")
    @patch("users.auth.max.services.MaxContactValidator.validate")
    @patch("users.auth.max.services.MaxInitDataValidator.validate")
    def test_verified_contact_binds_only_in_onec(self, validator, contact, client):
        validator.return_value = SimpleNamespace(
            user_id=int(MAX_ID), first_name="Ирина", last_name="Тестовая",
        )
        client.return_value.resolve.side_effect = [None, profile()]
        result = MaxAuthService.authenticate(
            init_data="signed-value", phone="+" + PHONE,
            phone_auth_date="123", phone_hash="signed",
        )
        self.assertIn("accessToken", result)
        self.assertEqual(client.return_value.resolve.call_count, 2)
        binding = client.return_value.resolve.call_args.kwargs
        self.assertEqual(binding["phone"], PHONE)
        self.assertNotIn("external_id", binding)
        contact.assert_called_once()

    @patch("users.auth.max.services.OneCMaxClient")
    def test_verified_max_code_creates_native_uuid_jwt(self, client):
        client.return_value.verify_code.return_value = profile(), None
        result = MaxAuthService.verify_code(phone="+" + PHONE, code="123456")
        self.assertEqual(AccessToken(result["accessToken"])["user_id"], ONEC_ID)

    @patch("users.auth.max.services.OneCMaxClient")
    def test_used_max_code_is_rejected(self, client):
        client.return_value.verify_code.return_value = None, "used"
        with self.assertRaises(AuthenticationFailed):
            MaxAuthService.verify_code(phone="+" + PHONE, code="123456")

    @patch.object(OneCMaxClient, "_post")
    def test_onec_max_client_sends_no_external_id(self, sender):
        sender.return_value = {"status": "ok", "user": profile()}
        result = OneCMaxClient().resolve(messenger_user_id=MAX_ID, phone=PHONE)
        self.assertEqual(result["onecId"], ONEC_ID)
        self.assertNotIn("externalId", sender.call_args.args[1])

    @patch.object(OneCMaxClient, "_post")
    def test_malformed_onec_max_role_is_refused(self, sender):
        sender.return_value = {
            "status": "ok", "user": {**profile(), "roles": ["unknown"]},
        }
        with self.assertRaises(OneCMaxError):
            OneCMaxClient().resolve(messenger_user_id=MAX_ID)
