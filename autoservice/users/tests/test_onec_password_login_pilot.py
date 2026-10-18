"""Login via existing 1C endpoint for bound accounts (isolated mocks)."""
import os
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
    @patch.dict(os.environ, {'ONEC_PASSWORD_LOGIN_ENABLED': ''})
    @patch('users.auth.services.User')
    @patch('users.auth.services.get_user_roles', return_value=['user'])
    @patch('users.auth.services.create_auth_tokens', return_value=TOKENS)
    @patch('users.auth.services.authenticate')
    @patch('users.auth.services.OneCPasswordAuthClient')
    def test_off_by_default_still_uses_django(
        self, client_type, authenticate, create_tokens, roles, user_model
    ):
        user = local_user()
        user_model.objects.filter.return_value.first.return_value = user
        authenticate.return_value = user
        self.assertEqual(AuthService.login(phone='+' + PHONE, password='old'), TOKENS)
        authenticate.assert_called_once_with(username=PHONE, password='old')
        client_type.assert_not_called()

    @patch.dict(os.environ, {'ONEC_PASSWORD_LOGIN_ENABLED': '1'})
    @patch('users.auth.services.User')
    @patch('users.auth.services.get_user_roles', return_value=['user'])
    @patch('users.auth.services.create_auth_tokens', return_value=TOKENS)
    @patch('users.auth.services.authenticate')
    @patch('users.auth.services.OneCPasswordAuthClient')
    def test_linked_account_verifies_1c_and_preserves_jwt_user(
        self, client_type, authenticate, create_tokens, roles, user_model
    ):
        user = local_user()
        user_model.objects.filter.return_value.first.return_value = user
        client_type.return_value.verify_password.return_value = remote_identity()
        self.assertEqual(
            AuthService.login(phone='+' + PHONE, password='new-1c-pass'), TOKENS
        )
        client_type.return_value.verify_password.assert_called_once_with(
            phone=PHONE, password='new-1c-pass'
        )
        user_model.objects.filter.assert_called_once_with(phone=PHONE)
        authenticate.assert_not_called()
        create_tokens.assert_called_once_with(user, active_role='user')

    @patch.dict(os.environ, {'ONEC_PASSWORD_LOGIN_ENABLED': '1'})
    @patch('users.auth.services.User')
    @patch('users.auth.services.authenticate')
    @patch('users.auth.services.OneCPasswordAuthClient')
    def test_rejected_1c_password_never_falls_back(
        self, client_type, authenticate, user_model
    ):
        user_model.objects.filter.return_value.first.return_value = local_user()
        client_type.return_value.verify_password.return_value = None
        with self.assertRaises(AuthenticationFailed):
            AuthService.login(phone=PHONE, password='old-django')
        authenticate.assert_not_called()

    @patch.dict(os.environ, {'ONEC_PASSWORD_LOGIN_ENABLED': '1'})
    @patch('users.auth.services.User')
    @patch('users.auth.services.OneCPasswordAuthClient')
    @patch('users.auth.services.authenticate')
    def test_native_identity_mismatch_refuses_login(
        self, authenticate, client_type, user_model
    ):
        client_type.return_value.verify_password.return_value = remote_identity()
        user_model.objects.filter.return_value.first.return_value = local_user(
            onec_id=UUID('22222222-2222-4222-8222-222222222222')
        )
        with self.assertRaises(AuthenticationFailed):
            AuthService.login(phone=PHONE, password='new-1c-pass')
        authenticate.assert_not_called()

    @patch.dict(os.environ, {'ONEC_PASSWORD_LOGIN_ENABLED': '1'})
    @patch('users.auth.services.User')
    @patch('users.auth.services.get_user_roles', return_value=['admin'])
    @patch('users.auth.services.OneCPasswordAuthClient')
    @patch('users.auth.services.authenticate')
    def test_role_mismatch_refuses_login(
        self, authenticate, client_type, roles, user_model
    ):
        client_type.return_value.verify_password.return_value = remote_identity()
        user_model.objects.filter.return_value.first.return_value = local_user()
        with self.assertRaises(AuthenticationFailed):
            AuthService.login(phone=PHONE, password='new-1c-pass')
        authenticate.assert_not_called()

    @patch.dict(os.environ, {'ONEC_PASSWORD_LOGIN_ENABLED': '1'})
    @patch('users.auth.services.authenticate')
    @patch('users.auth.services.OneCPasswordAuthClient')
    @patch('users.auth.services.User')
    def test_onec_outage_does_not_fall_back_to_django(
        self, user_model, client_type, authenticate
    ):
        user_model.objects.filter.return_value.first.return_value = local_user()
        client_type.return_value.verify_password.side_effect = OneCUserServiceError(
            'onec_auth_unavailable', 'Сервис проверки недоступен.', status_code=503
        )
        with self.assertRaises(OneCUserServiceError) as caught:
            AuthService.login(phone=PHONE, password='old-django')
        self.assertEqual(caught.exception.status_code, 503)
        authenticate.assert_not_called()

    @patch.dict(os.environ, {'ONEC_PASSWORD_LOGIN_ENABLED': '1'})
    @patch('users.auth.services.User')
    @patch('users.auth.services.authenticate')
    @patch('users.auth.services.get_user_roles', return_value=['user'])
    @patch('users.auth.services.create_auth_tokens', return_value=TOKENS)
    @patch('users.auth.services.OneCPasswordAuthClient')
    def test_unlinked_registration_remains_on_django(
        self, client_type, create_tokens, roles, authenticate, user_model
    ):
        user = local_user(onec_id=None)
        user_model.objects.filter.return_value.first.return_value = user
        authenticate.return_value = user
        self.assertEqual(AuthService.login(phone=PHONE, password='django'), TOKENS)
        authenticate.assert_called_once_with(username=PHONE, password='django')
        client_type.assert_not_called()

    @patch.dict(os.environ, {'ONEC_PASSWORD_LOGIN_ENABLED': '1'})
    def test_linked_account_cannot_change_only_django_password(self):
        user = Mock(phone=PHONE, onec_id=UUID(NATIVE))
        with self.assertRaises(ValidationError):
            AuthService.set_password(
                user=user, current_password='old', new_password='new',
            )
        user.has_usable_password.assert_not_called()
        user.set_password.assert_not_called()
        user.save.assert_not_called()

    @patch.dict(os.environ, {'ONEC_PASSWORD_LOGIN_ENABLED': '1'})
    def test_only_bound_users_switch(self):
        self.assertTrue(AuthService._uses_onec_password_login(local_user()))
        self.assertFalse(AuthService._uses_onec_password_login(local_user(onec_id=None)))
        self.assertFalse(AuthService._uses_onec_password_login(None))

    @patch.dict(os.environ, {'ONEC_PASSWORD_LOGIN_ENABLED': ''})
    def test_disabled_switch_never_uses_onec(self):
        self.assertFalse(AuthService._uses_onec_password_login(local_user()))
