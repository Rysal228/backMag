"""Password login is always delegated to 1C; Django retains JWT identities."""
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

from django.test import SimpleTestCase
from rest_framework.exceptions import AuthenticationFailed, ValidationError

from integrations.services.onec_users import OneCUserServiceError
from users.auth.services import AuthService


PHONE = '79135552525'
NATIVE = '37262ee6-c98a-11f1-9abc-fa163e59c328'
TOKENS = {'accessToken': 'access', 'refreshToken': 'refresh'}


def local_user(**overrides):
    data = {'phone': PHONE, 'onec_id': UUID(NATIVE), 'is_active': True}
    data.update(overrides)
    return SimpleNamespace(**data)


def remote_identity(**overrides):
    data = {'onecId': NATIVE, 'phone': PHONE, 'roles': ['user']}
    data.update(overrides)
    return data


class OneCPasswordLoginTests(SimpleTestCase):
    @patch('users.auth.services.User')
    @patch('users.auth.services.get_user_roles', return_value=['user'])
    @patch('users.auth.services.create_auth_tokens', return_value=TOKENS)
    @patch('users.auth.services.OneCPasswordAuthClient')
    def test_login_uses_1c_and_preserves_existing_jwt_user(
        self, client_type, create_tokens, roles, user_model
    ):
        user = local_user()
        user_model.objects.filter.return_value.first.return_value = user
        client_type.return_value.verify_password.return_value = remote_identity()
        self.assertEqual(
            AuthService.login(phone='+' + PHONE, password='new-1c-pass'),
            TOKENS,
        )
        client_type.return_value.verify_password.assert_called_once_with(
            phone=PHONE, password='new-1c-pass'
        )
        user_model.objects.filter.assert_called_once_with(phone=PHONE)
        create_tokens.assert_called_once_with(user, active_role='user')

    @patch('users.auth.services.User')
    @patch('users.auth.services.OneCPasswordAuthClient')
    def test_wrong_password_rejected_without_django_fallback(
        self, client_type, user_model
    ):
        client_type.return_value.verify_password.return_value = None
        with self.assertRaises(AuthenticationFailed):
            AuthService.login(phone=PHONE, password='wrong')
        user_model.objects.filter.assert_not_called()

    @patch('users.auth.services.User')
    @patch('users.auth.services.OneCPasswordAuthClient')
    def test_unknown_local_user_refuses_jwt(self, client_type, user_model):
        client_type.return_value.verify_password.return_value = remote_identity()
        user_model.objects.filter.return_value.first.return_value = None
        with self.assertRaises(AuthenticationFailed):
            AuthService.login(phone=PHONE, password='new-1c-pass')

    @patch('users.auth.services.User')
    @patch('users.auth.services.OneCPasswordAuthClient')
    def test_unlinked_local_user_refuses_jwt(self, client_type, user_model):
        client_type.return_value.verify_password.return_value = remote_identity()
        user_model.objects.filter.return_value.first.return_value = local_user(
            onec_id=None
        )
        with self.assertRaises(AuthenticationFailed):
            AuthService.login(phone=PHONE, password='new-1c-pass')

    @patch('users.auth.services.User')
    @patch('users.auth.services.OneCPasswordAuthClient')
    def test_native_identity_mismatch_refuses_login(
        self, client_type, user_model
    ):
        client_type.return_value.verify_password.return_value = remote_identity()
        user_model.objects.filter.return_value.first.return_value = local_user(
            onec_id=UUID('22222222-2222-4222-8222-222222222222')
        )
        with self.assertRaises(AuthenticationFailed):
            AuthService.login(phone=PHONE, password='new-1c-pass')

    @patch('users.auth.services.User')
    @patch('users.auth.services.get_user_roles', return_value=['admin'])
    @patch('users.auth.services.OneCPasswordAuthClient')
    def test_role_mismatch_refuses_login(
        self, client_type, roles, user_model
    ):
        client_type.return_value.verify_password.return_value = remote_identity()
        user_model.objects.filter.return_value.first.return_value = local_user()
        with self.assertRaises(AuthenticationFailed):
            AuthService.login(phone=PHONE, password='new-1c-pass')

    @patch('users.auth.services.User')
    @patch('users.auth.services.OneCPasswordAuthClient')
    def test_deactivated_local_user_refuses_login(
        self, client_type, user_model
    ):
        client_type.return_value.verify_password.return_value = remote_identity()
        user_model.objects.filter.return_value.first.return_value = local_user(
            is_active=False
        )
        with self.assertRaises(AuthenticationFailed):
            AuthService.login(phone=PHONE, password='new-1c-pass')

    @patch('users.auth.services.OneCPasswordAuthClient')
    def test_onec_unavailable_refuses_login(self, client_type):
        client_type.return_value.verify_password.side_effect = OneCUserServiceError(
            'onec_auth_unavailable', 'Временно недоступен.', status_code=503
        )
        with self.assertRaises(OneCUserServiceError) as caught:
            AuthService.login(phone=PHONE, password='old-django')
        self.assertEqual(caught.exception.status_code, 503)

    def test_password_change_cannot_write_only_django(self):
        user = Mock(phone=PHONE)
        with self.assertRaises(ValidationError):
            AuthService.set_password(
                user=user, current_password='old', new_password='new'
            )
        user.has_usable_password.assert_not_called()
        user.set_password.assert_not_called()
        user.save.assert_not_called()
