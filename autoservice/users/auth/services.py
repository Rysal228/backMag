"""Application authorization: 1C owns users, roles and password hashes."""
from rest_framework.exceptions import AuthenticationFailed, ValidationError

from integrations.services.onec_password_auth import OneCPasswordAuthClient
from integrations.services.onec_users import OneCUsersClient, OneCUserServiceError
from users.roles import get_user_roles, resolve_active_role

from .identity import native_id_from_profile, sync_native_user
from .role_selection import RoleSelectionService
from .tokens import create_auth_tokens, create_max_auth_tokens


class AuthService:
    @staticmethod
    def _tokens_or_role_selection(*, user, role=None):
        roles = get_user_roles(user)
        if role is not None:
            return create_auth_tokens(user, active_role=role)
        if len(roles) == 1:
            return create_auth_tokens(user, active_role=roles[0])
        return {
            "status": "role_selection_required",
            "roles": roles,
            "selectionToken": RoleSelectionService.create_token(
                user=user, auth_method="password",
            ),
        }

    @staticmethod
    def login(*, phone: str, password: str, role: str | None = None) -> dict:
        phone = PhoneNormalizer.normalize(phone)
        identity = OneCPasswordAuthClient().verify_password(
            phone=phone, password=password,
        )
        if identity is None:
            raise AuthenticationFailed("Неверный номер телефона или пароль.")

        profile = OneCUsersClient().get_user_by_onec_id(identity["onecId"])
        if (
            profile.get("phone") != phone
            or native_id_from_profile(profile) != identity["onecId"]
            or set(profile.get("roles", [])) != set(identity["roles"])
        ):
            raise OneCUserServiceError(
                "onec_identity_mismatch", "Сведения авторизации 1С не совпадают.",
            )
        user = sync_native_user(profile)
        return AuthService._tokens_or_role_selection(user=user, role=role)

    @staticmethod
    def register(
        *, phone: str, password: str, first_name: str,
        last_name: str, patronymic: str = "", birthday=None,
    ) -> dict:
        phone = PhoneNormalizer.normalize(phone)
        client = OneCUsersClient()
        # 1C creates the UUID; Django never generates an application-user UUID.
        native_id = client.create_user_with_password(
            phone=phone,
            password=password,
            first_name=first_name,
            last_name=last_name,
            patronymic=patronymic,
            birthday=birthday,
        )
        profile = client.get_user_by_onec_id(native_id)
        if profile.get("phone") != phone or profile.get("hasPassword") is not True:
            raise OneCUserServiceError(
                "onec_identity_mismatch", "1С вернула другую учётную запись.",
            )
        user = sync_native_user(profile)
        return AuthService._tokens_or_role_selection(user=user)

    @staticmethod
    def switch_role(*, user, role: str, token=None) -> dict[str, str]:
        profile = OneCUsersClient().get_user_by_onec_id(user.pk)
        current = sync_native_user(profile)
        selected = resolve_active_role(current, role)
        if token is not None and token.get("auth_method") == "max":
            from .max.services import MaxAuthService
            messenger_id = token.get("messenger_user_id", "")
            verified_phone = token.get("max_verified_phone", "")
            MaxAuthService.validate_current_binding(
                user=current, messenger_user_id=messenger_id,
                max_verified_phone=verified_phone,
            )
            return create_max_auth_tokens(
                current, messenger_user_id=messenger_id,
                max_verified_phone=verified_phone, active_role=selected,
            )
        return create_auth_tokens(current, active_role=selected)

    @staticmethod
    def set_password(*, user, current_password, new_password, token=None):
        client = OneCUsersClient()
        profile = client.get_user_by_onec_id(user.pk)
        if profile.get("isActive") is not True or profile.get("phone") != user.phone:
            raise AuthenticationFailed("Учётная запись больше не действительна.")

        if current_password:
            if new_password == current_password:
                raise ValidationError({
                    "newPassword": "Новый пароль должен отличаться от текущего.",
                })
            changed = OneCPasswordAuthClient().change_password(
                phone=user.phone, onec_id=user.pk,
                current_password=current_password, new_password=new_password,
            )
            if not changed:
                raise ValidationError({"currentPassword": "Неверный текущий пароль."})
            return

        # Setting an initial password without the old password is allowed
        # only after a validated MAX session and only when 1C has no password.
        if (
            token is None or token.get("auth_method") != "max"
            or not user.messenger_user_id
            or token.get("messenger_user_id") != user.messenger_user_id
            or token.get("max_verified_phone") != user.phone
        ):
            raise ValidationError({
                "currentPassword": "Для создания пароля подтвердите вход через MAX.",
            })
        from .max.services import MaxAuthService
        MaxAuthService.validate_current_binding(
            user=user, messenger_user_id=user.messenger_user_id,
            max_verified_phone=user.phone,
        )
        if (
            profile.get("hasPassword") is not False
            or profile.get("messengerUserId") != user.messenger_user_id
        ):
            raise ValidationError({
                "currentPassword": "Пароль уже установлен или MAX-привязка изменилась.",
            })
        OneCPasswordAuthClient().setup_initial_password(
            phone=user.phone, onec_id=user.pk, new_password=new_password,
        )


class PhoneNormalizer:
    @staticmethod
    def normalize(phone: str) -> str:
        phone = str(phone).strip().removeprefix("+")
        if (
            len(phone) != 11 or not phone.startswith("7")
            or not phone.isascii() or not phone.isdigit()
        ):
            raise ValidationError({"phone": "Invalid phone number."})
        return phone
