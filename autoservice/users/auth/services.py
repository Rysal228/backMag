import os

from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.hashers import check_password
from django.contrib.auth.password_validation import validate_password
from rest_framework.exceptions import AuthenticationFailed, ValidationError

from integrations.services.onec_password_auth import OneCPasswordAuthClient

from .role_selection import RoleSelectionService
from .tokens import create_auth_tokens, create_max_auth_tokens
from users.roles import get_user_roles, resolve_active_role

User = get_user_model()


class AuthService:
    @staticmethod
    def _uses_onec_password_login(user) -> bool:
        """Switch linked 1C users together when explicitly enabled.

        Unlinked accounts created by the existing registration flow continue
        to use Django passwords until registration is migrated to 1C.
        """
        return (
            os.environ.get('ONEC_PASSWORD_LOGIN_ENABLED') == '1'
            and user is not None
            and bool(user.onec_id)
        )

    @staticmethod
    def login(*, phone: str, password: str, role: str | None = None) -> dict[str, str]:
        phone = PhoneNormalizer.normalize(phone)
        user = User.objects.filter(phone=phone).first()

        if AuthService._uses_onec_password_login(user):
            # Linked accounts: never fall back to the old Django hash when
            # 1C rejects a password or its protected service is unavailable.
            identity = OneCPasswordAuthClient().verify_password(
                phone=phone, password=password,
            )
            if identity is None:
                raise AuthenticationFailed(
                    'Неверный номер телефона или пароль.'
                )

            # Preserve legacy Django user_id and FK relations. Never trust
            # a phone match alone: 1C's native UUID must be bound locally.
            if (
                user is None
                or not user.is_active
                or not user.onec_id
                or str(user.onec_id) != identity['onecId']
            ):
                raise AuthenticationFailed(
                    'Неверный номер телефона или пароль.'
                )

            # Until roles migrate, refuse inconsistent role assignments
            # instead of accidentally granting stale or elevated access.
            if set(get_user_roles(user)) != set(identity['roles']):
                raise AuthenticationFailed(
                    'Роли пользователя требуют синхронизации с 1С.'
                )
        else:
            user = authenticate(
                username=phone,
                password=password,
            )
            if user is None:
                raise AuthenticationFailed(
                    'Неверный номер телефона или пароль.'
                )

        if not user.is_active:
            raise AuthenticationFailed(
                'Пользователь деактивирован.'
            )

        roles = get_user_roles(user)

        if role is not None:
            return create_auth_tokens(user, active_role=role)

        if len(roles) == 1:
            return create_auth_tokens(user, active_role=roles[0])

        return {
            'status': 'role_selection_required',
            'roles': roles,
            'selectionToken': RoleSelectionService.create_token(
                user=user,
                auth_method='password',
            ),
        }

    @staticmethod
    def switch_role(*, user, role: str, token=None) -> dict[str, str]:
        active_role = resolve_active_role(user, role)

        if token is not None and token.get('auth_method') == 'max':
            return create_max_auth_tokens(
                user,
                messenger_user_id=token.get('messenger_user_id', ''),
                max_verified_phone=token.get('max_verified_phone', ''),
                active_role=active_role,
            )

        return create_auth_tokens(user, active_role=active_role)

    @staticmethod
    def register(
        *,
        phone: str,
        password: str,
        first_name: str,
        last_name: str,
        patronymic: str = '',
        birthday=None,
    ) -> dict[str, str]:
        phone = PhoneNormalizer.normalize(phone)

        if User.objects.filter(phone=phone).exists():
            raise ValidationError({
                'phone': 'User with this phone already exists.',
            })

        user = User.objects.create_user(
            phone=phone,
            password=password,
            first_name=first_name,
            last_name=last_name,
            patronymic=patronymic,
            birthday=birthday,
        )

        return create_auth_tokens(user)

    @staticmethod
    def set_password(
        *,
        user,
        current_password: str | None,
        new_password: str,
    ) -> None:
        # Do not check an obsolete Django hash or write a new Django hash
        # after this account has switched to 1C password verification.
        if AuthService._uses_onec_password_login(user):
            raise ValidationError({
                'newPassword': 'Смена пароля этого аккаунта будет доступна после переноса в 1С.'
            })

        if user.has_usable_password():
            if not current_password or not check_password(
                current_password,
                user.password,
            ):
                raise ValidationError({
                    'currentPassword': 'Неверный текущий пароль.'
                })

        validate_password(new_password, user)

        user.set_password(new_password)
        user.save(update_fields=['password'])


class PhoneNormalizer:

    @staticmethod
    def normalize(phone: str) -> str:
        phone = phone.strip()

        if phone.startswith('+'):
            phone = phone[1:]

        if not phone.isdigit():
            raise ValidationError({
                'phone': 'Invalid phone number.',
            })

        return phone
