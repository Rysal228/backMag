"""Site authentication regressions: native 1C UUID, no Django application user."""
from unittest.mock import patch
from uuid import UUID

from django.test import SimpleTestCase
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from users.auth.identity import OneCUser, user_from_profile
from users.auth.services import AuthService
from users.auth.tokens import (
    create_auth_tokens, create_max_auth_tokens, rotate_refresh_token,
    revoke_refresh_token, validate_token_subject,
)
from users.authentication import RoleJWTAuthentication


ONEC_ID = "d2b65827-0e38-48b8-a27e-4aef3ce3c135"
PHONE = "79135572795"
MAX = "987654321"


def onec_profile(*, roles=None, max_id="", active=True, has_password=True):
    return {
        "onecId": ONEC_ID, "phone": PHONE,
        "roles": ["user"] if roles is None else roles,
        "isActive": active, "hasPassword": has_password,
        "messengerUserId": max_id,
        "firstName": "Анна", "lastName": "Тестовая",
        "patronymic": "", "birthday": None,
    }


class NativeIdentityTests(SimpleTestCase):
    def test_current_onec_profile_yields_authenticated_non_orm_user(self):
        user = user_from_profile(onec_profile())
        self.assertIsInstance(user, OneCUser)
        self.assertEqual(user.pk, UUID(ONEC_ID))
        self.assertTrue(user.is_authenticated)
        self.assertTrue(user.has_role("user"))
        self.assertEqual(user.get_full_name(), "Тестовая Анна")

    def test_deactivated_user_refused(self):
        with self.assertRaises(AuthenticationFailed):
            user_from_profile(onec_profile(active=False))

    def test_role_list_must_be_unique_and_nonempty(self):
        for roles in ([], ["user", "user"], ["unknown"]):
            with self.subTest(roles=roles), self.assertRaises(Exception):
                user_from_profile(onec_profile(roles=roles))

    def test_issuance_uses_native_id_without_orm_row(self):
        result = create_auth_tokens(user_from_profile(onec_profile()))
        access = AccessToken(result["accessToken"])
        refresh = RefreshToken(result["refreshToken"])
        self.assertEqual(access["user_id"], ONEC_ID)
        self.assertEqual(refresh["user_id"], ONEC_ID)
        self.assertEqual(access["active_role"], "user")
        self.assertEqual(access["auth_method"], "password")

    def test_max_claims_included_and_bound(self):
        user = user_from_profile(onec_profile(max_id=MAX))
        result = create_max_auth_tokens(
            user, messenger_user_id=MAX, max_verified_phone=PHONE,
        )
        access = AccessToken(result["accessToken"])
        self.assertEqual(access["messenger_user_id"], MAX)
        self.assertEqual(access["max_verified_phone"], PHONE)

    @patch("users.auth.tokens.OneCUsersClient")
    def test_access_token_resolves_only_current_1c_user(self, client):
        client.return_value.get_user_by_onec_id.return_value = onec_profile()
        jwt = create_auth_tokens(user_from_profile(onec_profile()))["accessToken"]
        token = RoleJWTAuthentication().get_validated_token(jwt)
        user = RoleJWTAuthentication().get_user(token)
        self.assertEqual(user.id, UUID(ONEC_ID))
        client.return_value.get_user_by_onec_id.assert_called_once_with(ONEC_ID)

    @patch("users.auth.tokens.OneCUsersClient")
    def test_access_token_rejects_role_revoked_in_1c(self, client):
        user = user_from_profile(onec_profile(roles=["user", "mechanic"]))
        jwt = create_auth_tokens(user, active_role="mechanic")["accessToken"]
        client.return_value.get_user_by_onec_id.return_value = onec_profile()
        token = RoleJWTAuthentication().get_validated_token(jwt)
        with self.assertRaises(AuthenticationFailed):
            RoleJWTAuthentication().get_user(token)

    @patch("users.auth.tokens.OneCUsersClient")
    def test_max_session_rejected_after_rebinding(self, client):
        user = user_from_profile(onec_profile(max_id=MAX))
        jwt = create_max_auth_tokens(
            user, messenger_user_id=MAX, max_verified_phone=PHONE,
        )["accessToken"]
        client.return_value.get_user_by_onec_id.return_value = onec_profile(max_id="different")
        token = RoleJWTAuthentication().get_validated_token(jwt)
        with self.assertRaises(AuthenticationFailed):
            RoleJWTAuthentication().get_user(token)


class AuthServiceNativeTests(SimpleTestCase):
    @patch("users.auth.services.create_auth_tokens")
    @patch("users.auth.services.OneCUsersClient")
    @patch("users.auth.services.OneCPasswordAuthClient")
    def test_password_login_needs_only_onec_user(self, password, client, tokens):
        password.return_value.verify_password.return_value = {
            "onecId": ONEC_ID, "phone": PHONE, "roles": ["user"],
        }
        client.return_value.get_user_by_onec_id.return_value = onec_profile()
        tokens.return_value = {"accessToken": "test", "refreshToken": "test"}
        result = AuthService.login(phone="+" + PHONE, password="password")
        self.assertEqual(result["accessToken"], "test")
        client.return_value.get_user_by_onec_id.assert_called_once_with(ONEC_ID)

    @patch("users.auth.services.OneCUsersClient")
    @patch("users.auth.services.create_auth_tokens")
    def test_registration_uses_onec_generated_uuid(self, tokens, client):
        client.return_value.create_user_with_password.return_value = ONEC_ID
        client.return_value.get_user_by_onec_id.return_value = onec_profile()
        tokens.return_value = {"accessToken": "test", "refreshToken": "test"}
        AuthService.register(
            phone="+" + PHONE, password="samplepassword",
            first_name="Анна", last_name="Тестовая",
        )
        sent = client.return_value.create_user_with_password.call_args.kwargs
        self.assertNotIn("external_id", sent)
        client.return_value.get_user_by_onec_id.assert_called_once_with(ONEC_ID)


class RefreshRevocationTests(SimpleTestCase):
    @patch("users.auth.tokens.RevokedRefreshToken")
    @patch("users.auth.tokens.OneCUsersClient")
    @patch("users.auth.tokens.transaction.atomic")
    def test_refresh_rotates_and_consumes_old_jti(self, atomic, client, table):
        client.return_value.get_user_by_onec_id.return_value = onec_profile()
        table.objects.get_or_create.return_value = (object(), True)
        old = create_auth_tokens(user_from_profile(onec_profile()))
        updated = rotate_refresh_token(old["refreshToken"])
        self.assertNotEqual(updated["refreshToken"], old["refreshToken"])
        self.assertIn("accessToken", updated)
        self.assertEqual(table.objects.get_or_create.call_count, 1)

    @patch("users.auth.tokens.RevokedRefreshToken")
    @patch("users.auth.tokens.OneCUsersClient")
    @patch("users.auth.tokens.transaction.atomic")
    def test_replayed_refresh_is_rejected(self, atomic, client, table):
        client.return_value.get_user_by_onec_id.return_value = onec_profile()
        table.objects.get_or_create.return_value = (object(), False)
        old = create_auth_tokens(user_from_profile(onec_profile()))
        with self.assertRaises(AuthenticationFailed):
            rotate_refresh_token(old["refreshToken"])

    @patch("users.auth.tokens.RevokedRefreshToken")
    @patch("users.auth.tokens.transaction.atomic")
    def test_logout_rejects_other_user_refresh(self, atomic, table):
        current = user_from_profile(onec_profile())
        attacker = OneCUser(id=UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc"),
                           phone=PHONE, roles=("user",))
        raw = create_auth_tokens(current)["refreshToken"]
        with self.assertRaises(AuthenticationFailed):
            revoke_refresh_token(raw, user=attacker, access_token={"auth_method": "password"})
        table.objects.get_or_create.assert_not_called()
