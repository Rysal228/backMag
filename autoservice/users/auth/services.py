from django.contrib.auth import get_user_model
from rest_framework.exceptions import AuthenticationFailed, ValidationError

from integrations.services.onec_password_auth import OneCPasswordAuthClient

from .role_selection import RoleSelectionService
from .tokens import create_auth_tokens, create_max_auth_tokens
from users.roles import get_user_roles, resolve_active_role

User = get_user_model()


class AuthService:
    @staticmethod
    def login(*, phone: str, password: str, role: str | None = None) -> dict[str, str]:
        phone = PhoneNormalizer.normalize(phone)

        # 1C is authoritative for password verification; no Django fallback.
        identity = OneCPasswordAuthClient().verify_password(
            phone=phone, password=password,
        )
        if identity is None:
            raise AuthenticationFailed(
                'Неверный номер телефона или пароль.'
            )

        # Django still owns JWT/FK identity during the migration.
        user = User.objects.filter(phone=phone).first()
        if (
            user is None
            or not user.is_active
            or not user.onec_id
            or str(user.onec_id) != identity['onecId']
        ):
            raise AuthenticationFailed(
                'Неверный номер телефона или пароль.'
            )

        if set(get_user_roles(user)) != set(identity['roles']):
            raise AuthenticationFailed(
                'Роли пользователя требуют синхронизации с 1С.'
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
        # Never change only Django's obsolete hash: 1C is the password store.
        raise ValidationError({
            'newPassword': 'Изменение пароля через сайт пока недоступно. Пароль хранится в 1С.'
        })


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
