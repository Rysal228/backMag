"""Password login is always delegated to 1C; Django retains JWT identities."""
from types import SimpleNamespace
from contextlib import nullcontext
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

    @patch('users.auth.services.OneCPasswordAuthClient')
    def test_password_change_uses_only_onec(self, client_type):
        user = Mock(phone=PHONE, onec_id=UUID(NATIVE), is_active=True)
        client_type.return_value.change_password.return_value = True
        AuthService.set_password(
            user=user, current_password='original-pass', new_password='new-pass',
        )
        client_type.return_value.change_password.assert_called_once_with(
            phone=PHONE, onec_id=UUID(NATIVE),
            current_password='original-pass', new_password='new-pass',
        )
        user.set_password.assert_not_called()
        user.save.assert_not_called()

    @patch('users.auth.services.OneCPasswordAuthClient')
    def test_password_change_wrong_current_password(self, client_type):
        user = Mock(phone=PHONE, onec_id=UUID(NATIVE), is_active=True)
        client_type.return_value.change_password.return_value = False
        with self.assertRaises(ValidationError):
            AuthService.set_password(
                user=user, current_password='wrong', new_password='new-pass'
            )
        user.set_password.assert_not_called()
        user.save.assert_not_called()

    @patch('users.auth.services.OneCPasswordAuthClient')
    def test_same_new_password_rejected_before_1c_call(self, client_type):
        user = Mock(phone=PHONE, onec_id=UUID(NATIVE), is_active=True)
        with self.assertRaises(ValidationError) as caught:
            AuthService.set_password(
                user=user, current_password='same-password-123',
                new_password='same-password-123',
            )
        self.assertIn('newPassword', caught.exception.detail)
        client_type.assert_not_called()

    @patch('users.auth.services.OneCPasswordAuthClient')
    def test_max_only_without_onec_id_cannot_change_password(self, client_type):
        user = Mock(phone=PHONE, onec_id=None, is_active=True)
        with self.assertRaises(ValidationError):
            AuthService.set_password(
                user=user, current_password='original', new_password='new-pass'
            )
        client_type.assert_not_called()

    @patch('users.auth.services.OneCPasswordAuthClient')
    def test_first_password_rejects_password_jwt_without_max_claims(self, auth_client):
        user = Mock(
            pk=UUID('44d93602-a058-4896-9f68-181bb34b4af3'),
            phone=PHONE, onec_id=None, is_active=True,
            messenger_user_id='max-user-123',
        )
        with self.assertRaises(ValidationError) as caught:
            AuthService.set_password(
                user=user, current_password=None,
                new_password='new-synthetic-password',
                token={'auth_method': 'password'},
            )
        self.assertIn('currentPassword', caught.exception.detail)
        auth_client.assert_not_called()

    @patch('users.auth.services.OneCUsersClient')
    @patch('users.auth.services.OneCPasswordAuthClient')
    def test_first_password_rejects_max_session_from_another_phone(
        self, auth_client, onec_client
    ):
        user = Mock(
            pk=UUID('44d93602-a058-4896-9f68-181bb34b4af3'),
            phone=PHONE, onec_id=None, is_active=True,
            messenger_user_id='max-user-123',
        )
        with self.assertRaises(ValidationError):
            AuthService.set_password(
                user=user, current_password=None,
                new_password='new-synthetic-password',
                token={'auth_method': 'max',
                       'messenger_user_id': 'max-user-123',
                       'max_verified_phone': '79999999999'},
            )
        auth_client.assert_not_called()
        onec_client.assert_not_called()

    @patch('users.auth.services.transaction.atomic', return_value=nullcontext())
    @patch('users.auth.services.get_user_roles', return_value=['user'])
    @patch('users.auth.services.User')
    @patch('users.auth.services.OneCPasswordAuthClient')
    @patch('users.auth.services.OneCUsersClient')
    def test_first_password_creates_onec_for_unlinked_max_user(
        self, onec_type, auth_type, user_type, roles, atomic
    ):
        local_id = UUID('44d93602-a058-4896-9f68-181bb34b4af3')
        user = Mock(
            pk=local_id, phone=PHONE, onec_id=None, is_active=True,
            messenger_user_id='max-user-123', first_name='Иван',
            last_name='Иванов', patronymic='', birthday=None,
        )
        user_type.objects.select_for_update.return_value.get.return_value = user
        onec_type.return_value.get_user.side_effect = OneCUserServiceError(
            'onec_user_not_found', 'Не найден.', status_code=404,
        )
        onec_type.return_value.create_user_with_password.return_value = NATIVE
        AuthService.set_password(
            user=user, current_password=None,
            new_password='new-synthetic-password',
            token={'auth_method': 'max',
                   'messenger_user_id': 'max-user-123',
                   'max_verified_phone': PHONE},
        )
        onec_type.return_value.create_user_with_password.assert_called_once_with(
            phone=PHONE, external_id=local_id, password='new-synthetic-password',
            first_name='Иван', last_name='Иванов', patronymic='',
            birthday=None, messenger_user_id='max-user-123',
            roles=['user'],
        )
        self.assertEqual(user.onec_id, NATIVE)
        user.save.assert_called_once_with(update_fields=['onec_id'])
        auth_type.assert_not_called()
        user.set_password.assert_not_called()

    @patch('users.auth.services.transaction.atomic', return_value=nullcontext())
    @patch('users.auth.services.get_user_roles', return_value=['user'])
    @patch('users.auth.services.User')
    @patch('users.auth.services.OneCPasswordAuthClient')
    @patch('users.auth.services.OneCUsersClient')
    def test_first_password_sets_only_empty_register_for_existing_onec(
        self, onec_type, auth_type, user_type, roles, atomic
    ):
        local_id = UUID('44d93602-a058-4896-9f68-181bb34b4af3')
        user = Mock(
            pk=local_id, phone=PHONE, onec_id=UUID(NATIVE),
            is_active=True, messenger_user_id='max-user-123',
        )
        user_type.objects.select_for_update.return_value.get.return_value = user
        onec_type.return_value.get_user.return_value = {
            'onecId': NATIVE, 'externalId': str(local_id),
            'phone': PHONE, 'isActive': True, 'hasPassword': False,
            'roles': ['user'], 'messengerUserId': 'max-user-123',
        }
        AuthService.set_password(
            user=user, current_password=None,
            new_password='new-synthetic-password',
            token={'auth_method': 'max',
                   'messenger_user_id': 'max-user-123',
                   'max_verified_phone': PHONE},
        )
        auth_type.return_value.setup_initial_password.assert_called_once_with(
            phone=PHONE, onec_id=NATIVE, external_id=local_id,
            new_password='new-synthetic-password',
        )
        onec_type.return_value.create_user_with_password.assert_not_called()
        user.save.assert_not_called()

    @patch('users.auth.services.transaction.atomic', return_value=nullcontext())
    @patch('users.auth.services.get_user_roles', return_value=['user'])
    @patch('users.auth.services.User')
    @patch('users.auth.services.OneCPasswordAuthClient')
    @patch('users.auth.services.OneCUsersClient')
    def test_first_password_cannot_replace_existing_hash(
        self, onec_type, auth_type, user_type, roles, atomic
    ):
        local_id = UUID('44d93602-a058-4896-9f68-181bb34b4af3')
        user = Mock(
            pk=local_id, phone=PHONE, onec_id=UUID(NATIVE),
            is_active=True, messenger_user_id='max-user-123',
        )
        user_type.objects.select_for_update.return_value.get.return_value = user
        onec_type.return_value.get_user.return_value = {
            'onecId': NATIVE, 'externalId': str(local_id),
            'phone': PHONE, 'isActive': True, 'hasPassword': True,
            'roles': ['user'], 'messengerUserId': 'max-user-123',
        }
        with self.assertRaises(OneCUserServiceError) as caught:
            AuthService.set_password(
                user=user, current_password=None,
                new_password='new-synthetic-password',
                token={'auth_method': 'max',
                       'messenger_user_id': 'max-user-123',
                       'max_verified_phone': PHONE},
            )
        self.assertEqual(caught.exception.status_code, 409)
        auth_type.assert_not_called()
