from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.exceptions import AuthenticationFailed, ValidationError

from integrations.services.onec_password_auth import OneCPasswordAuthClient
from integrations.services.onec_users import OneCUsersClient, OneCUserServiceError

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
        if token is not None and token.get('auth_method') == 'max':
            from .max.services import MaxAuthService
            MaxAuthService.validate_current_binding(
                user=user,
                messenger_user_id=token.get('messenger_user_id', ''),
                max_verified_phone=token.get('max_verified_phone', ''),
            )
            active_role = resolve_active_role(user, role)
            return create_max_auth_tokens(
                user,
                messenger_user_id=token.get('messenger_user_id', ''),
                max_verified_phone=token.get('max_verified_phone', ''),
                active_role=active_role,
            )

        active_role = resolve_active_role(user, role)
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

        # Keep only Django identity and role relations for JWT and existing
        # cars/orders; 1C owns the credential and its salted stored hash.
        # No usable Django password is ever written during registration.
        with transaction.atomic():
            user = User.objects.create_user(
                phone=phone,
                password=None,
                first_name=first_name,
                last_name=last_name,
                patronymic=patronymic,
                birthday=birthday,
            )

            native_id = OneCUsersClient().create_user_with_password(
                phone=phone,
                external_id=user.pk,
                password=password,
                first_name=first_name,
                last_name=last_name,
                patronymic=patronymic,
                birthday=birthday,
            )
            user.onec_id = native_id
            user.save(update_fields=['onec_id'])

        return create_auth_tokens(user)

    @staticmethod
    def _validate_password_setup_session(*, user, token) -> None:
        # Only a server-validated MAX JWT bound to the current phone and MAX ID
        # is eligible to set the FIRST password. Password/anonymous tokens
        # must never turn an empty register into account takeover.
        if (
            token is None
            or token.get('auth_method') != 'max'
            or not user.messenger_user_id
            or token.get('messenger_user_id') != user.messenger_user_id
            or token.get('max_verified_phone') != user.phone
        ):
            raise ValidationError({
                'currentPassword': 'Для создания пароля подтвердите вход через MAX.'
            })

        # Compatibility for pre-migration MAX sessions with no 1C identity.
        # The subsequent 1C password setup path still checks native identity,
        # externalId, phone and MAX ID before creating a password.
        if not user.onec_id:
            return

        from .max.services import MaxAuthService
        try:
            MaxAuthService.validate_current_binding(
                user=user,
                messenger_user_id=user.messenger_user_id,
                max_verified_phone=user.phone,
            )
        except AuthenticationFailed as exc:
            raise ValidationError({
                'currentPassword': 'Повторно подтвердите вход через MAX.'
            }) from exc

    @staticmethod
    def _validate_onec_setup_profile(*, user, profile) -> str:
        """Never attach a different 1C user, even when phone matches."""
        from uuid import UUID
        try:
            native_id = str(UUID(str(profile['onecId'])))
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            raise OneCUserServiceError(
                'onec_identity_mismatch', '1С вернула некорректного пользователя.',
                status_code=409,
            ) from exc

        if (
            profile.get('externalId') != str(user.pk)
            or profile.get('phone') != user.phone
            or profile.get('isActive') is not True
            or profile.get('hasPassword') is not False
            or set(profile.get('roles', [])) != set(get_user_roles(user))
            or (profile.get('messengerUserId') and
                profile['messengerUserId'] != user.messenger_user_id)
            or (user.onec_id and native_id != str(user.onec_id))
        ):
            raise OneCUserServiceError(
                'onec_identity_mismatch',
                'Аккаунт уже имеет пароль или сведения 1С не совпадают.',
                status_code=409,
            )
        return native_id

    @staticmethod
    def set_password(
        *,
        user,
        current_password: str | None,
        new_password: str,
        token=None,
    ) -> None:
        if not user.is_active:
            raise ValidationError({'newPassword': 'Аккаунт неактивен.'})

        if current_password:
            # Existing password: always verify it in 1C, never in Django.
            if not user.onec_id:
                raise ValidationError({
                    'currentPassword': 'Аккаунт ещё не связан с 1С.'
                })
            if new_password == current_password:
                raise ValidationError({
                    'newPassword': 'Новый пароль должен отличаться от текущего.'
                })
            changed = OneCPasswordAuthClient().change_password(
                phone=user.phone,
                onec_id=user.onec_id,
                current_password=current_password,
                new_password=new_password,
            )
            if not changed:
                raise ValidationError({
                    'currentPassword': 'Неверный текущий пароль.'
                })
            return

        # No current password: setup is permitted only via authenticated MAX
        # session. The 1C register is the authoritative no-password check.
        AuthService._validate_password_setup_session(user=user, token=token)

        with transaction.atomic():
            locked = User.objects.select_for_update().get(pk=user.pk)
            if (
                not locked.is_active
                or locked.phone != user.phone
                or locked.messenger_user_id != user.messenger_user_id
            ):
                raise ValidationError({
                    'currentPassword': 'Повторно подтвердите аккаунт через MAX.'
                })

            client = OneCUsersClient()
            if locked.onec_id:
                profile = client.get_user(locked.phone)
                native_id = AuthService._validate_onec_setup_profile(
                    user=locked, profile=profile,
                )
                OneCPasswordAuthClient().setup_initial_password(
                    phone=locked.phone,
                    onec_id=native_id,
                    external_id=locked.pk,
                    new_password=new_password,
                )
                return

            # MAX can create a local identity before 1C migration. If an
            # already-imported native user exists, bind only matching IDs.
            try:
                profile = client.get_user(locked.phone)
            except OneCUserServiceError as exc:
                if exc.status_code != 404:
                    raise
                profile = None

            if profile is not None:
                native_id = AuthService._validate_onec_setup_profile(
                    user=locked, profile=profile,
                )
                OneCPasswordAuthClient().setup_initial_password(
                    phone=locked.phone,
                    onec_id=native_id,
                    external_id=locked.pk,
                    new_password=new_password,
                )
            else:
                native_id = client.create_user_with_password(
                    phone=locked.phone,
                    external_id=locked.pk,
                    password=new_password,
                    first_name=locked.first_name,
                    last_name=locked.last_name,
                    patronymic=locked.patronymic,
                    birthday=locked.birthday,
                    messenger_user_id=locked.messenger_user_id,
                    roles=get_user_roles(locked),
                )

            locked.onec_id = native_id
            locked.save(update_fields=['onec_id'])


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
