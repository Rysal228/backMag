"""Temporary ORM adapter keyed exclusively by the native 1C catalog UUID.

This bridge exists only while car/order/chat ForeignKeys target CustomUser.
It never allocates a second application-user identifier.
"""
from uuid import UUID

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from rest_framework.exceptions import AuthenticationFailed

from integrations.services.onec_users import OneCUserServiceError
from users.models import UserRoleAssignment

User = get_user_model()
VALID_ROLES = frozenset({"user", "mechanic", "admin"})


def native_id_from_profile(profile):
    try:
        value = str(UUID(str(profile["onecId"])))
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise OneCUserServiceError(
            "onec_invalid_response", "1С вернула некорректный UUID пользователя."
        ) from exc
    return value


def sync_native_user(profile):
    """Mirror an authenticated 1C profile using pk == its native onecId."""
    native_id = native_id_from_profile(profile)
    phone = profile.get("phone")
    roles = profile.get("roles")
    messenger = profile.get("messengerUserId") or ""

    if (
        not isinstance(phone, str) or len(phone) != 11
        or not phone.startswith("7") or not phone.isascii() or not phone.isdigit()
        or profile.get("isActive") is not True
        or not isinstance(roles, list) or not roles
        or len(roles) != len(set(roles))
        or not set(roles) <= VALID_ROLES
        or not isinstance(messenger, str)
    ):
        raise AuthenticationFailed("Учётная запись неактивна или данные 1С некорректны.")

    try:
        with transaction.atomic():
            user = User.objects.select_for_update().filter(pk=native_id).first()
            by_phone = User.objects.select_for_update().filter(phone=phone).first()
            if by_phone is not None and str(by_phone.pk) != native_id:
                # Legacy Django UUIDs cannot be silently claimed as native IDs.
                raise OneCUserServiceError(
                    "onec_native_id_conflict",
                    "В PostgreSQL осталась учётная запись со старым UUID. Требуется очистка тестовых данных.",
                    status_code=409,
                )
            if messenger:
                by_max = User.objects.select_for_update().filter(
                    messenger_user_id=messenger,
                ).first()
                if by_max is not None and str(by_max.pk) != native_id:
                    raise OneCUserServiceError(
                        "onec_native_id_conflict",
                        "MAX уже связан с другой локальной записью.",
                        status_code=409,
                    )

            if user is None:
                user = User.objects.create_user(
                    id=UUID(native_id),
                    phone=phone,
                    password=None,
                    first_name=profile.get("firstName") or "",
                    last_name=profile.get("lastName") or "",
                    patronymic=profile.get("patronymic") or "",
                    messenger_user_id=messenger or None,
                    onec_id=UUID(native_id),
                )
            else:
                if user.phone != phone or (user.onec_id and str(user.onec_id) != native_id):
                    raise OneCUserServiceError(
                        "onec_native_id_conflict", "Локальный UUID не соответствует 1С.",
                        status_code=409,
                    )
                fields = []
                mirror = {
                    "onec_id": UUID(native_id),
                    "is_active": True,
                    "messenger_user_id": messenger or None,
                    "first_name": profile.get("firstName") or "",
                    "last_name": profile.get("lastName") or "",
                    "patronymic": profile.get("patronymic") or "",
                }
                for name, value in mirror.items():
                    if getattr(user, name) != value:
                        setattr(user, name, value)
                        fields.append(name)
                if fields:
                    user.save(update_fields=fields)

            UserRoleAssignment.objects.filter(user=user).exclude(role__in=roles).delete()
            for role in roles:
                UserRoleAssignment.objects.get_or_create(user=user, role=role)
            return user
    except IntegrityError as exc:
        raise OneCUserServiceError(
            "onec_native_id_conflict", "Не удалось связать UUID пользователя 1С.",
            status_code=409,
        ) from exc
