"""MAX authentication: Django verifies MAX signatures; 1C owns the account.

Django uses the native catalog UUID as the sole identity. The frontend contract is unchanged.
"""

import secrets
import uuid

from rest_framework.exceptions import APIException, AuthenticationFailed

from integrations.services.onec_max import OneCMaxClient, OneCMaxError
from users.roles import get_user_roles
from ..identity import native_id_from_profile, sync_native_user
from ..role_selection import RoleSelectionService
from ..services import PhoneNormalizer
from ..tokens import create_max_auth_tokens
from .client import MaxBotApiError, MaxBotClient
from .validators import MaxContactValidator, MaxInitDataValidator


class MaxAccountConflict(APIException):
    status_code = 409
    default_code = "max_account_conflict"
    default_detail = (
        "Этот номер телефона или аккаунт MAX уже связан "
        "с другой учётной записью."
    )


class MaxCodeDeliveryError(APIException):
    status_code = 502
    default_code = "max_code_delivery_failed"
    default_detail = "Не удалось отправить код в MAX."


class MaxAuthService:
    @staticmethod
    def _create_tokens_or_selection(*, user, role, messenger_user_id):
        roles = get_user_roles(user)
        if role is not None:
            return create_max_auth_tokens(
                user, messenger_user_id=messenger_user_id,
                max_verified_phone=user.phone, active_role=role,
            )
        if len(roles) == 1:
            return create_max_auth_tokens(
                user, messenger_user_id=messenger_user_id,
                max_verified_phone=user.phone, active_role=roles[0],
            )
        return {
            "status": "role_selection_required",
            "roles": roles,
            "selectionToken": RoleSelectionService.create_token(
                user=user, auth_method="max",
                messenger_user_id=messenger_user_id,
                max_verified_phone=user.phone,
            ),
        }

    @staticmethod
    def _sync_identity(profile):
        return sync_native_user(profile)

    @staticmethod
    def authenticate(
        *,
        init_data: str,
        phone: str | None = None,
        phone_auth_date: str | None = None,
        phone_hash: str | None = None,
        force_contact: bool = False,
        role: str | None = None,
    ):
        max_data = MaxInitDataValidator.validate(init_data)
        max_id = str(max_data.user_id)

        if phone is not None:
            phone = PhoneNormalizer.normalize(phone)
            MaxContactValidator.validate(
                phone=phone,
                auth_date=phone_auth_date,
                received_hash=phone_hash,
                user_id=max_data.user_id,
            )

        if force_contact and phone is None:
            return {"status": "contact_required"}

        client = OneCMaxClient()
        profile = client.resolve(messenger_user_id=max_id)

        if profile is None:
            if phone is None:
                return {"status": "contact_required"}
            profile = client.resolve(
                messenger_user_id=max_id,
                phone=phone,
                first_name=max_data.first_name,
                last_name=max_data.last_name,
            )
            if profile is None or profile.get("phone") != phone:
                raise OneCMaxError(
                    "onec_max_identity_mismatch",
                    "1С не выполнила привязку MAX к указанному телефону.",
                )

        if profile["messengerUserId"] != max_id:
            raise OneCMaxError(
                "onec_max_identity_mismatch", "1С вернула другой MAX-аккаунт."
            )
        if phone is not None and profile["phone"] != phone:
            raise MaxAccountConflict()

        user = MaxAuthService._sync_identity(profile)
        return MaxAuthService._create_tokens_or_selection(
            user=user, role=role, messenger_user_id=max_id,
        )

    @staticmethod
    def validate_current_binding(*, user, messenger_user_id, max_verified_phone):
        """Re-check MAX session against the native 1C user and the signed binding."""
        if (
            not user.is_active
            or user.messenger_user_id != messenger_user_id
            or user.phone != max_verified_phone
            or not messenger_user_id
        ):
            raise AuthenticationFailed("MAX-сессия больше не действительна.")
        profile = OneCMaxClient().resolve(messenger_user_id=messenger_user_id)
        if (
            profile is None
            or native_id_from_profile(profile) != str(user.pk)
            or profile["phone"] != user.phone
            or profile["messengerUserId"] != messenger_user_id
            or set(profile["roles"]) != set(get_user_roles(user))
        ):
            raise AuthenticationFailed("MAX-сессия больше не действительна.")

    @staticmethod
    def request_code(*, phone: str):
        phone = PhoneNormalizer.normalize(phone)
        code = f"{secrets.randbelow(1_000_000):06d}"
        request_id = str(uuid.uuid4())
        client = OneCMaxClient()
        messenger_id = client.issue_code(
            phone=phone, code=code, request_id=request_id,
        )
        try:
            MaxBotClient().send_message_to_user(
                user_id=messenger_id,
                text=(
                    "Код для входа в автосервис: "
                    f"{code}\n\n"
                    "Код действует 5 минут. Никому его не сообщайте."
                ),
            )
        except MaxBotApiError as exc:
            try:
                client.cancel_code(phone=phone, request_id=request_id)
            except OneCMaxError:
                # Do not mask delivery failure or leak the challenge.
                pass
            raise MaxCodeDeliveryError() from exc

    @staticmethod
    def verify_code(*, phone: str, code: str, role: str | None = None):
        phone = PhoneNormalizer.normalize(phone)
        profile, reason = OneCMaxClient().verify_code(phone=phone, code=code)
        if profile is None:
            messages = {
                "invalid": "Неверный номер телефона или код.",
                "used": "Код уже использован.",
                "expired": "Срок действия кода истёк.",
                "attempts": "Превышено количество попыток ввода кода.",
            }
            raise AuthenticationFailed(messages[reason])

        if profile["phone"] != phone:
            raise OneCMaxError(
                "onec_max_identity_mismatch", "1С вернула другой номер телефона."
            )
        user = MaxAuthService._sync_identity(profile)
        return MaxAuthService._create_tokens_or_selection(
            user=user, role=role, messenger_user_id=profile["messengerUserId"],
        )
