"""Regression tests for trusted MAX -> Django gateway -> 1C auth boundary."""

from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

from django.test import SimpleTestCase, TestCase, override_settings
from rest_framework.exceptions import AuthenticationFailed

from integrations.services.onec_max import OneCMaxClient, OneCMaxError
from users.auth.max.services import (
    MaxAccountConflict, MaxAuthService, MaxCodeDeliveryError,
)
from users.auth.max.client import MaxBotApiError
from users.models import CustomUser, MaxAuthCode, UserRoleAssignment


PHONE = "79135552525"
ONEC_ID = "37262ee6-c98a-11f1-9abc-fa163e59c328"
EXTERNAL_ID = "e3124aa4-6bb6-48ab-b070-0df3bfcbe26f"
MAX_ID = "123456789"


def profile(**changes):
    data = {
        "onecId": ONEC_ID,
        "externalId": EXTERNAL_ID,
        "phone": PHONE,
        "messengerUserId": MAX_ID,
        "firstName": "Иван",
        "lastName": "Иванов",
        "roles": ["user"],
        "isActive": True,
    }
    data.update(changes)
    return data


class MaxTransferTests(TestCase):
    def test_missing_contact_never_creates_account(self):
        with patch("users.auth.max.services.MaxInitDataValidator.validate",
                   return_value=SimpleNamespace(user_id=int(MAX_ID))), \
             patch("users.auth.max.services.OneCMaxClient") as gateway:
            gateway.return_value.resolve.return_value = None
            result = MaxAuthService.authenticate(init_data="signed")
        self.assertEqual(result, {"status": "contact_required"})
        self.assertEqual(CustomUser.objects.count(), 0)

    def test_verified_contact_creates_both_identity_and_unusable_django_password(self):
        with patch("users.auth.max.services.MaxInitDataValidator.validate",
                   return_value=SimpleNamespace(
                       user_id=int(MAX_ID), first_name="Иван",
                       last_name="Иванов",
                   )), \
             patch("users.auth.max.services.uuid.uuid4", return_value=UUID(EXTERNAL_ID)), \
             patch("users.auth.max.services.MaxContactValidator.validate") as contact, \
             patch("users.auth.max.services.OneCMaxClient") as gateway, \
             patch("users.auth.max.services.create_max_auth_tokens",
                   return_value={"accessToken": "access", "refreshToken": "refresh"}):
            gateway.return_value.resolve.side_effect = [None, profile()]
            result = MaxAuthService.authenticate(
                init_data="signed", phone="+" + PHONE,
                phone_auth_date="date", phone_hash="sig",
            )
            self.assertIn("accessToken", result)
            contact.assert_called_once()
            self.assertEqual(gateway.return_value.resolve.call_count, 2)
            self.assertIsNotNone(gateway.return_value.resolve.call_args.kwargs['external_id'])
        user = CustomUser.objects.get(phone=PHONE)
        # 1C created account first and Django only retained a JWT/FK mirror.
        self.assertFalse(user.has_usable_password())
        self.assertEqual(str(user.onec_id), ONEC_ID)
        self.assertEqual(user.messenger_user_id, MAX_ID)
        self.assertEqual(set(user.get_roles()), {"user"})

    def test_existing_max_does_not_request_contact_again(self):
        user = CustomUser.objects.create_user(
            id=UUID(EXTERNAL_ID), phone=PHONE, password=None,
            messenger_user_id=MAX_ID,
        )
        with patch("users.auth.max.services.MaxInitDataValidator.validate",
                   return_value=SimpleNamespace(user_id=int(MAX_ID))), \
             patch("users.auth.max.services.OneCMaxClient") as gateway, \
             patch("users.auth.max.services.MaxContactValidator.validate") as contact, \
             patch("users.auth.max.services.create_max_auth_tokens",
                   return_value={"accessToken": "a", "refreshToken": "r"}):
            gateway.return_value.resolve.return_value = profile()
            MaxAuthService.authenticate(init_data="signed")
            contact.assert_not_called()
        user.refresh_from_db()
        self.assertEqual(str(user.onec_id), ONEC_ID)

    def test_different_local_user_with_same_phone_blocks_token(self):
        CustomUser.objects.create_user(phone=PHONE, password=None)
        with self.assertRaises(MaxAccountConflict), \
             patch("users.auth.max.services.MaxInitDataValidator.validate",
                   return_value=SimpleNamespace(user_id=int(MAX_ID))), \
             patch("users.auth.max.services.OneCMaxClient") as gateway:
            gateway.return_value.resolve.return_value = profile()
            MaxAuthService.authenticate(init_data="signed")

    def test_existing_roles_are_synchronized_from_1c(self):
        user = CustomUser.objects.create_user(
            phone=PHONE, password=None,
            id=UUID(EXTERNAL_ID), messenger_user_id=MAX_ID,
        )
        with patch("users.auth.max.services.MaxInitDataValidator.validate",
                   return_value=SimpleNamespace(user_id=int(MAX_ID))), \
             patch("users.auth.max.services.OneCMaxClient") as gateway:
            gateway.return_value.resolve.return_value = profile(roles=["mechanic", "admin"])
            outcome = MaxAuthService.authenticate(init_data="signed")
        self.assertEqual(outcome["status"], "role_selection_required")
        self.assertEqual(set(outcome["roles"]), {"mechanic", "admin"})
        self.assertEqual(
            set(UserRoleAssignment.objects.filter(user=user).values_list("role", flat=True)),
            {"mechanic", "admin"},
        )

    def test_onec_unavailable_never_uses_local_max_auth_fallback(self):
        CustomUser.objects.create_user(
            phone=PHONE, messenger_user_id=MAX_ID, password=None,
        )
        with patch("users.auth.max.services.MaxInitDataValidator.validate",
                   return_value=SimpleNamespace(user_id=int(MAX_ID))), \
             patch("users.auth.max.services.OneCMaxClient") as gateway:
            gateway.return_value.resolve.side_effect = OneCMaxError(
                "onec_max_unavailable", "1С недоступна."
            )
            with self.assertRaises(OneCMaxError):
                MaxAuthService.authenticate(init_data="signed")

    def test_delivery_failure_cancels_only_issued_code(self):
        with patch("users.auth.max.services.OneCMaxClient") as gateway, \
             patch("users.auth.max.services.MaxBotClient") as bot, \
             patch("users.auth.max.services.secrets.randbelow", return_value=123):
            gateway.return_value.issue_code.return_value = MAX_ID
            bot.return_value.send_message_to_user.side_effect = MaxBotApiError()
            with self.assertRaises(MaxCodeDeliveryError):
                MaxAuthService.request_code(phone=PHONE)
            sent = gateway.return_value.issue_code.call_args.kwargs
            self.assertEqual(sent["code"], "000123")
            gateway.return_value.cancel_code.assert_called_once_with(
                phone=PHONE, request_id=sent["request_id"]
            )
        self.assertEqual(MaxAuthCode.objects.count(), 0)

    def test_verify_code_accepts_only_onec_verified_identity(self):
        with patch("users.auth.max.services.OneCMaxClient") as gateway, \
             patch("users.auth.max.services.create_max_auth_tokens",
                   return_value={"accessToken": "a", "refreshToken": "r"}):
            gateway.return_value.verify_code.return_value = (profile(), None)
            self.assertIn("accessToken", MaxAuthService.verify_code(
                phone=PHONE, code="123456"
            ))
        self.assertFalse(CustomUser.objects.get(phone=PHONE).has_usable_password())
        self.assertEqual(MaxAuthCode.objects.count(), 0)

    def test_used_code_denied(self):
        with patch("users.auth.max.services.OneCMaxClient") as gateway:
            gateway.return_value.verify_code.return_value = (None, "used")
            with self.assertRaises(AuthenticationFailed):
                MaxAuthService.verify_code(phone=PHONE, code="123456")
        self.assertEqual(CustomUser.objects.count(), 0)


class OneCMaxClientTests(SimpleTestCase):
    @patch.dict("os.environ", {
        "ONEC_MAX_BASE_URL": "http://host.docker.internal:8081/ServiceCar/hs/api",
        "ONEC_MAX_API_USER": "servicecar-auth",
        "ONEC_MAX_API_PASSWORD": "password",
    })
    @patch("integrations.services.onec_max.requests.post")
    def test_existing_internal_apache_http_api_is_supported(self, post):
        post.return_value = Mock(status_code=200, json=lambda: {
            "status": "ok", "user": profile(),
        })
        self.assertEqual(
            OneCMaxClient().resolve(messenger_user_id=MAX_ID), profile()
        )
        self.assertEqual(
            post.call_args.args[0],
            "http://host.docker.internal:8081/ServiceCar/hs/api/max/resolve",
        )
        self.assertEqual(
            post.call_args.kwargs["auth"], ("servicecar-auth", "password")
        )
        self.assertFalse(post.call_args.kwargs["allow_redirects"])

    @patch.dict("os.environ", {
        "ONEC_MAX_BASE_URL": "http://onec.example.test/ServiceCar/hs/api",
        "ONEC_MAX_API_USER": "servicecar-auth",
        "ONEC_MAX_API_PASSWORD": "password",
    })
    def test_http_on_other_hosts_is_rejected(self):
        with self.assertRaises(OneCMaxError):
            OneCMaxClient()

    @patch.dict("os.environ", {
        "ONEC_MAX_BASE_URL": "http://host.docker.internal:8082/ServiceCar/hs/api",
        "ONEC_MAX_API_USER": "servicecar-auth",
        "ONEC_MAX_API_PASSWORD": "password",
    })
    def test_http_on_other_ports_is_rejected(self):
        with self.assertRaises(OneCMaxError):
            OneCMaxClient()

    @patch.dict("os.environ", {
        "ONEC_MAX_BASE_URL": "http://host.docker.internal:8081/ServiceCar/hs/api",
        "ONEC_MAX_API_USER": "servicecar-auth",
        "ONEC_MAX_API_PASSWORD": "",
    })
    def test_basic_credentials_remain_required(self):
        with self.assertRaises(OneCMaxError):
            OneCMaxClient()

    @patch.dict("os.environ", {
        "ONEC_MAX_BASE_URL": "http://host.docker.internal:8081/ServiceCar/hs/api",
        "ONEC_MAX_API_USER": "servicecar-auth",
        "ONEC_MAX_API_PASSWORD": "password",
    })
    def test_default_internal_url_when_env_unset(self):
        with patch.dict("os.environ", {}, clear=True):
            with patch.dict("os.environ", {
                "ONEC_AUTH_API_USER": "servicecar-auth",
                "ONEC_AUTH_API_PASSWORD": "password",
            }):
                client = OneCMaxClient()
        self.assertEqual(
            client.base_url, "http://host.docker.internal:8081/ServiceCar/hs/api"
        )
        self.assertEqual(
            (client.username, client.password), ("servicecar-auth", "password")
        )

    @patch.dict("os.environ", {
        "ONEC_MAX_BASE_URL": "https://onec.example.test/ServiceCar/hs/api",
        "ONEC_MAX_API_USER": "servicecar-auth",
        "ONEC_MAX_API_PASSWORD": "password",
    })
    @patch("integrations.services.onec_max.requests.post")
    def test_https_also_supported_and_never_follows_redirect(self, post):
        post.return_value = Mock(status_code=200, json=lambda: {
            "status": "ok", "user": profile(),
        })
        self.assertEqual(
            OneCMaxClient().resolve(messenger_user_id=MAX_ID), profile()
        )
        self.assertFalse(post.call_args.kwargs["allow_redirects"])
        self.assertEqual(post.call_args.kwargs["auth"][0], "servicecar-auth")
        self.assertEqual(post.call_args.kwargs["timeout"], 10)

    @patch.dict("os.environ", {
        "ONEC_MAX_BASE_URL": "https://onec.example.test/ServiceCar/hs/api",
        "ONEC_MAX_API_USER": "servicecar-auth",
        "ONEC_MAX_API_PASSWORD": "password",
    })
    @patch("integrations.services.onec_max.requests.post")
    def test_conflict_from_1c_stays_conflict_not_local_fallback(self, post):
        post.return_value = Mock(
            status_code=409,
            json=lambda: {"code": "max_account_conflict"},
        )
        with self.assertRaises(OneCMaxError) as err:
            OneCMaxClient().resolve(messenger_user_id=MAX_ID)
        self.assertEqual(err.exception.status_code, 409)

    def test_profile_mismatch_and_malformed_roles_fail_closed(self):
        for modified in (
            profile(onecId="not-a-uuid"),
            profile(roles=[{"role": "admin"}]),
            profile(isActive="yes"),
        ):
            with self.subTest(modified=modified), self.assertRaises(OneCMaxError):
                OneCMaxClient._profile(modified)
