"""Regression coverage: app auth never creates a Django user row."""
from datetime import datetime, timezone
from unittest.mock import Mock, patch
from uuid import UUID

from django.test import SimpleTestCase, TestCase
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from integrations.services.onec_max import OneCMaxClient
from integrations.services.onec_users import OneCUsersClient
from users.auth.identity import sync_native_user
from users.auth.services import AuthService
from users.auth.tokens import create_auth_tokens, create_max_auth_tokens
from users.auth.token_rotation import rotate_refresh, logout_refresh
from users.authentication import validate_native_claims

NATIVE = "d2b65827-0e38-48b8-a27e-4aef3ce3c135"
PHONE = "79135572795"
MAX_ID = "123456789"


def profile(**overrides):
    data = {
        "onecId": NATIVE, "phone": PHONE,
        "firstName": "Ирина", "lastName": "Тестовая",
        "patronymic": "", "birthday": None, "roles": ["user"],
        "messengerUserId": "", "isActive": True, "hasPassword": True,
    }
    data.update(overrides)
    return data


class NativeIdentityTests(SimpleTestCase):
    def test_native_identity_is_not_django_model(self):
        user = sync_native_user(profile())
        self.assertEqual(user.pk, UUID(NATIVE))
        self.assertTrue(user.is_authenticated)
        self.assertEqual(user.get_roles(), ["user"])
        self.assertEqual(user.get_full_name(), "Тестовая Ирина")
        self.assertFalse(hasattr(user, "save"))

    def test_deactivated_and_invalid_roles_are_rejected(self):
        for bad in (profile(isActive=False), profile(roles=["superuser"])):
            with self.subTest(bad=bad):
                with self.assertRaises(AuthenticationFailed):
                    sync_native_user(bad)

    @patch("users.auth.services.OneCUsersClient")
    @patch("users.auth.services.OneCPasswordAuthClient")
    def test_password_login_without_local_user(self, passwords, users):
        passwords.return_value.verify_password.return_value = {
            "onecId": NATIVE, "phone": PHONE, "roles": ["user"],
        }
        users.return_value.get_user_by_onec_id.return_value = profile()
        result = AuthService.login(phone="+" + PHONE, password="test")
        self.assertIn("accessToken", result)
        self.assertEqual(AccessToken(result["accessToken"])["user_id"], NATIVE)

    @patch("users.auth.services.OneCUsersClient")
    def test_register_uses_onec_id_directly(self, users):
        users.return_value.create_user_with_password.return_value = NATIVE
        users.return_value.get_user_by_onec_id.return_value = profile()
        result = AuthService.register(
            phone="+" + PHONE, password="correct-horse-example",
            first_name="Ирина", last_name="Тестовая",
        )
        self.assertIn("refreshToken", result)
        self.assertEqual(RefreshToken(result["refreshToken"])["user_id"], NATIVE)
        self.assertNotIn(
            "external_id",
            users.return_value.create_user_with_password.call_args.kwargs,
        )

    @patch("users.authentication.OneCUsersClient")
    def test_role_revocation_blocks_existing_access_token(self, users):
        tokens = create_auth_tokens(sync_native_user(profile()))
        users.return_value.get_user_by_onec_id.return_value = profile(roles=["admin"])
        with self.assertRaises(AuthenticationFailed):
            validate_native_claims(AccessToken(tokens["accessToken"]))

    @patch("users.authentication.OneCUsersClient")
    def test_max_binding_changes_block_token(self, users):
        user = sync_native_user(profile(messengerUserId=MAX_ID))
        tokens = create_max_auth_tokens(
            user, messenger_user_id=MAX_ID, max_verified_phone=PHONE,
        )
        users.return_value.get_user_by_onec_id.return_value = profile(
            messengerUserId="another-max-user",
        )
        with self.assertRaises(AuthenticationFailed):
            validate_native_claims(AccessToken(tokens["accessToken"]))

    @patch("integrations.services.onec_users.requests.request")
    def test_new_user_payload_has_no_second_uuid(self, request):
        reply = Mock(status_code=201, ok=True)
        reply.json.return_value = {"user": profile()}
        request.return_value = reply
        result = OneCUsersClient().create_user_with_password(
            phone=PHONE, password="example-password-123",
            first_name="Ирина", last_name="Тестовая",
        )
        self.assertEqual(result, NATIVE)
        self.assertNotIn("externalId", request.call_args.kwargs["json"])

    @patch.object(OneCMaxClient, "_post")
    def test_max_resolve_requires_no_second_uuid(self, post):
        post.return_value = {"status": "ok", "user": profile(messengerUserId=MAX_ID)}
        result = OneCMaxClient().resolve(
            messenger_user_id=MAX_ID, phone=PHONE,
        )
        self.assertEqual(result["onecId"], NATIVE)
        self.assertNotIn("externalId", post.call_args.args[1])


class RefreshRevocationTests(TestCase):
    @patch("users.authentication.OneCUsersClient")
    def test_refresh_can_only_rotate_once(self, users):
        user = sync_native_user(profile())
        old = create_auth_tokens(user)["refreshToken"]
        users.return_value.get_user_by_onec_id.return_value = profile()
        tokens = rotate_refresh(old)
        self.assertIn("accessToken", tokens)
        self.assertNotEqual(old, tokens["refreshToken"])
        with self.assertRaises(AuthenticationFailed):
            rotate_refresh(old)

    @patch("users.authentication.OneCUsersClient")
    def test_logout_rejects_reuse(self, users):
        user = sync_native_user(profile())
        old = create_auth_tokens(user)["refreshToken"]
        logout_refresh(old, user)
        users.return_value.get_user_by_onec_id.return_value = profile()
        with self.assertRaises(AuthenticationFailed):
            rotate_refresh(old)
