"""MAX authentication: Django verifies MAX signatures; 1C owns the account.

Django temporarily maintains UUID/JWT/FK identity until cars/orders and JWT
move to native 1C IDs. The frontend contract is unchanged.
"""

import secrets
import uuid

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from rest_framework.exceptions import APIException, AuthenticationFailed

from integrations.services.onec_max import OneCMaxClient, OneCMaxError
from users.models import UserRoleAssignment
from users.roles import get_user_roles
from ..role_selection import RoleSelectionService
from ..services import PhoneNormalizer
from ..tokens import create_max_auth_tokens
from .client import MaxBotApiError, MaxBotClient
from .validators import MaxContactValidator, MaxInitDataValidator


User = get_user_model()


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
        """Accept identity only after an authenticated 1C response.

        Refuse mismatches; do not overwrite legacy UUID/phone/native binding.
        Local roles are just a temporary mirror for existing JWT and FK checks.
        """
        identity_id = uuid.UUID(profile["externalId"])
        phone = profile["phone"]
        messenger_id = profile["messengerUserId"]
        roles = set(profile["roles"])

        try:
            with transaction.atomic():
                user = User.objects.select_for_update().filter(pk=identity_id).first()
                by_phone = User.objects.select_for_update().filter(phone=phone).first()
                by_max = User.objects.select_for_update().filter(
                    messenger_user_id=messenger_id,
                ).first()
                if (
                    (by_phone is not None and by_phone.pk != identity_id)
                    or (by_max is not None and by_max.pk != identity_id)
                ):
                    raise MaxAccountConflict()
                if user is None:
                    user = User.objects.create_user(
                        id=identity_id,
                        phone=phone,
                        password=None,
                        messenger_user_id=messenger_id,
                        first_name=profile["firstName"],
                        last_name=profile["lastName"],
                    )
                elif (
                    user.phone != phone
                    or not user.is_active
                    or (user.messenger_user_id
                        and user.messenger_user_id != messenger_id)
                ):
                    raise MaxAccountConflict()

                changes = []
                if user.messenger_user_id != messenger_id:
                    user.messenger_user_id = messenger_id
                    changes.append("messenger_user_id")
                # A deleted 1C catalog item gets a new native UUID if the same
                # MAX account logs in again. 1C has already verified the
                # MAX ID, phone and immutable Django externalId. Restore the
                # native link instead of stranding the existing Django user.
                native_id = uuid.UUID(profile["onecId"])
                if user.onec_id != native_id:
                    if User.objects.select_for_update().filter(
                        onec_id=native_id,
                    ).exclude(pk=identity_id).exists():
                        raise MaxAccountConflict()
                    user.onec_id = native_id
                    changes.append("onec_id")
                if changes:
                    user.save(update_fields=changes)

                # Only the verified native account's roles are authoritative.
                UserRoleAssignment.objects.filter(user=user).exclude(
                    role__in=roles,
                ).delete()
                for assigned in roles:
                    UserRoleAssignment.objects.get_or_create(user=user, role=assigned)
                return user
        except IntegrityError as exc:
            raise MaxAccountConflict() from exc

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
            # Older MAX identities may exist only in Django. The saved binding
            # is trusted here only because this MAX ID was just HMAC-verified.
            historical = User.objects.filter(messenger_user_id=max_id).first()
            if historical is not None and not historical.is_active:
                raise AuthenticationFailed("User is inactive.")

            if phone is None:
                if historical is None:
                    return {"status": "contact_required"}
                phone = historical.phone
            elif historical is not None and historical.phone != phone:
                raise MaxAccountConflict()

            local = User.objects.filter(phone=phone).first()
            if local is not None and (
                not local.is_active
                or (local.messenger_user_id and local.messenger_user_id != max_id)
            ):
                raise MaxAccountConflict()

            external_id = local.pk if local is not None else uuid.uuid4()
            profile = client.resolve(
                messenger_user_id=max_id,
                phone=phone,
                external_id=external_id,
                first_name=max_data.first_name,
                last_name=max_data.last_name,
            )
            if profile is None:
                raise OneCMaxError(
                    "onec_max_bad_response", "1С не выполнила привязку MAX."
                )
            if (
                profile["externalId"] != str(external_id)
                or profile["phone"] != phone
            ):
                raise OneCMaxError(
                    "onec_max_identity_mismatch", "1С вернула другую учётную запись."
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
        """Fail closed on role/binding changes even for an existing MAX JWT."""
        if (
            not user.is_active
            or user.messenger_user_id != messenger_user_id
            or user.phone != max_verified_phone
            or not user.onec_id
        ):
            raise AuthenticationFailed("MAX-сессия больше не действительна.")
        profile = OneCMaxClient().resolve(messenger_user_id=messenger_user_id)
        if (
            profile is None
            or profile["externalId"] != str(user.pk)
            or profile["onecId"] != str(user.onec_id)
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
