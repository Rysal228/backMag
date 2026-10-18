"""Registration keeps the Django JWT identity but stores the password only in 1C."""
from contextlib import nullcontext
from datetime import date
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

from django.test import SimpleTestCase

from integrations.services.onec_users import OneCUserServiceError, OneCUsersClient
from users.auth.services import AuthService


PHONE = "79135552525"
LEGACY_ID = "e3124aa4-6bb6-48ab-b070-0df3bfcbe26f"
NATIVE_ID = "37262ee6-c98a-11f1-9abc-fa163e59c328"
TOKENS = {"accessToken": "access", "refreshToken": "refresh"}


def remote_user():
    return {
        "onecId": NATIVE_ID,
        "externalId": LEGACY_ID,
        "phone": PHONE,
        "firstName": "Иван",
        "lastName": "Иванов",
        "patronymic": "",
        "birthday": None,
        "roles": ["user"],
        "isActive": True,
        "hasPassword": True,
    }


class OneCRegistrationServiceTests(SimpleTestCase):
    @patch("users.auth.services.transaction.atomic", return_value=nullcontext())
    @patch("users.auth.services.create_auth_tokens", return_value=TOKENS)
    @patch("users.auth.services.OneCUsersClient")
    @patch("users.auth.services.User")
    def test_registration_creates_unusable_django_password_and_binds_1c(
        self, user_type, onec_type, tokens, atomic
    ):
        user_type.objects.filter.return_value.exists.return_value = False
        user = Mock(pk=UUID(LEGACY_ID), onec_id=None)
        user_type.objects.create_user.return_value = user
        onec_type.return_value.create_user_with_password.return_value = NATIVE_ID

        result = AuthService.register(
            phone="+" + PHONE,
            password="test-registration-password",
            first_name="Иван",
            last_name="Иванов",
        )
        self.assertEqual(result, TOKENS)
        self.assertEqual(
            user_type.objects.create_user.call_args.kwargs["password"],
            None,
        )
        onec_type.return_value.create_user_with_password.assert_called_once_with(
            phone=PHONE,
            external_id=user.pk,
            password="test-registration-password",
            first_name="Иван",
            last_name="Иванов",
            patronymic="",
            birthday=None,
        )
        self.assertEqual(user.onec_id, NATIVE_ID)
        user.save.assert_called_once_with(update_fields=["onec_id"])
        tokens.assert_called_once_with(user)

    @patch("users.auth.services.transaction.atomic", return_value=nullcontext())
    @patch("users.auth.services.create_auth_tokens")
    @patch("users.auth.services.OneCUsersClient")
    @patch("users.auth.services.User")
    def test_1c_failure_does_not_issue_tokens(
        self, user_type, onec_type, tokens, atomic
    ):
        user_type.objects.filter.return_value.exists.return_value = False
        user_type.objects.create_user.return_value = Mock(pk=UUID(LEGACY_ID))
        onec_type.return_value.create_user_with_password.side_effect = (
            OneCUserServiceError("onec_unavailable", "1С недоступна.")
        )
        with self.assertRaises(OneCUserServiceError):
            AuthService.register(
                phone="+" + PHONE, password="test-registration-password",
                first_name="Иван", last_name="Иванов",
            )
        tokens.assert_not_called()

    @patch("users.auth.services.OneCUsersClient")
    @patch("users.auth.services.User")
    def test_existing_django_phone_never_contacts_1c(self, user_type, onec_type):
        user_type.objects.filter.return_value.exists.return_value = True
        from rest_framework.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            AuthService.register(
                phone="+" + PHONE, password="test-registration-password",
                first_name="Иван", last_name="Иванов",
            )
        onec_type.assert_not_called()


class OneCRegistrationClientTests(SimpleTestCase):
    @patch("integrations.services.onec_users.requests.request")
    @patch.dict("os.environ", {
        "ONEC_BASE_URL": "http://host.docker.internal:8081",
        "ONEC_USERS_PATH": "/ServiceCar/hs/api/user",
        "ONEC_API_USER": "",
        "ONEC_API_PASSWORD": "",
    })
    def test_posts_new_user_to_1c_with_password(self, request):
        request.side_effect = [
            Mock(status_code=200, json=lambda: {"passwordRegistration": True}),
            Mock(ok=True, status_code=201, json=lambda: {"user": remote_user()}),
        ]
        native_id = OneCUsersClient().create_user_with_password(
            phone="+" + PHONE,
            external_id=UUID(LEGACY_ID),
            password="test-registration-password",
            first_name="Иван", last_name="Иванов",
            birthday=None,
        )
        self.assertEqual(native_id, NATIVE_ID)
        kwargs = request.call_args.kwargs
        self.assertEqual(request.call_count, 2)
        self.assertEqual(request.call_args_list[0].args[0], "GET")
        self.assertTrue(request.call_args_list[0].args[1].endswith("/user/profile"))
        self.assertEqual(request.call_args.args[0], "POST")
        self.assertTrue(request.call_args.args[1].endswith("/ServiceCar/hs/api/user"))
        self.assertEqual(kwargs["json"]["externalId"], LEGACY_ID)
        self.assertEqual(kwargs["json"]["password"], "test-registration-password")
        self.assertEqual(kwargs["json"]["roles"], ["user"])
        self.assertFalse(kwargs["allow_redirects"])

    @patch("integrations.services.onec_users.requests.request")
    @patch.dict("os.environ", {
        "ONEC_BASE_URL": "http://host.docker.internal:8081",
        "ONEC_USERS_PATH": "/ServiceCar/hs/api/user",
        "ONEC_API_USER": "",
        "ONEC_API_PASSWORD": "",
    })
    def test_mismatched_native_identity_is_rejected(self, request):
        bad = dict(remote_user(), externalId="aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa")
        request.side_effect = [
            Mock(status_code=200, json=lambda: {"passwordRegistration": True}),
            Mock(ok=True, status_code=201, json=lambda: {"user": bad}),
        ]
        with self.assertRaises(OneCUserServiceError):
            OneCUsersClient().create_user_with_password(
                phone=PHONE,
                external_id=LEGACY_ID,
                password="test-registration-password",
                first_name="Иван", last_name="Иванов",
            )

    @patch("integrations.services.onec_users.requests.request")
    @patch.dict("os.environ", {
        "ONEC_BASE_URL": "http://host.docker.internal:8081",
        "ONEC_USERS_PATH": "/ServiceCar/hs/api/user",
        "ONEC_API_USER": "",
        "ONEC_API_PASSWORD": "",
    })
    def test_1c_duplicate_phone_surfaces_conflict(self, request):
        request.side_effect = [
            Mock(status_code=200, json=lambda: {"passwordRegistration": True}),
            Mock(
                ok=False, status_code=409,
                json=lambda: {"code": "user_exists", "message": "Уже существует."},
            ),
        ]
        with self.assertRaises(OneCUserServiceError) as caught:
            OneCUsersClient().create_user_with_password(
                phone=PHONE,
                external_id=LEGACY_ID,
                password="test-registration-password",
                first_name="Иван", last_name="Иванов",
            )
        self.assertEqual(caught.exception.status_code, 409)

    @patch("integrations.services.onec_users.requests.request")
    @patch.dict("os.environ", {
        "ONEC_BASE_URL": "http://host.docker.internal:8081",
        "ONEC_USERS_PATH": "/ServiceCar/hs/api/user",
        "ONEC_API_USER": "",
        "ONEC_API_PASSWORD": "",
    })
    def test_old_1c_does_not_create_passwordless_account(self, request):
        request.return_value = Mock(
            status_code=200, json=lambda: {"result": "ok"}
        )
        with self.assertRaises(OneCUserServiceError) as caught:
            OneCUsersClient().create_user_with_password(
                phone=PHONE,
                external_id=LEGACY_ID,
                password="test-registration-password",
                first_name="Иван", last_name="Иванов",
            )
        self.assertEqual(caught.exception.status_code, 503)
        request.assert_called_once()
        self.assertEqual(request.call_args.args[0], "GET")



class OneCPasswordStatusTests(SimpleTestCase):
    @patch("users.auth.views.OneCUsersClient")
    def test_status_reads_onec_register_not_django_hash(self, client_type):
        from rest_framework.test import APIRequestFactory, force_authenticate
        from users.auth.views import PasswordView
        user = SimpleNamespace(
            pk=UUID(LEGACY_ID),
            onec_id=UUID(NATIVE_ID),
            phone=PHONE,
            is_authenticated=True,
        )
        client_type.return_value.get_user.return_value = dict(
            remote_user(), hasPassword=True
        )
        request = APIRequestFactory().get("/api/v1/users/auth/password/")
        force_authenticate(request, user=user)
        response = PasswordView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"hasPassword": True})
        client_type.return_value.get_user.assert_called_once_with(PHONE)

    @patch("users.auth.views.OneCUsersClient")
    def test_status_fails_on_remote_user_mismatch(self, client_type):
        from rest_framework.test import APIRequestFactory, force_authenticate
        from users.auth.views import PasswordView
        user = SimpleNamespace(
            pk=UUID(LEGACY_ID),
            onec_id=UUID(NATIVE_ID),
            phone=PHONE,
            is_authenticated=True,
        )
        client_type.return_value.get_user.return_value = dict(
            remote_user(),
            externalId="aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa",
            hasPassword=True,
        )
        request = APIRequestFactory().get("/api/v1/users/auth/password/")
        force_authenticate(request, user=user)
        response = PasswordView.as_view()(request)
        self.assertEqual(response.status_code, 502)

    @patch("users.auth.views.OneCUsersClient")
    def test_unlinked_max_only_user_has_no_onec_password(self, client_type):
        from rest_framework.test import APIRequestFactory, force_authenticate
        from users.auth.views import PasswordView
        user = SimpleNamespace(
            pk=UUID(LEGACY_ID),
            onec_id=None,
            phone=PHONE,
            is_authenticated=True,
        )
        request = APIRequestFactory().get("/api/v1/users/auth/password/")
        force_authenticate(request, user=user)
        response = PasswordView.as_view()(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"hasPassword": False})
        client_type.assert_not_called()
