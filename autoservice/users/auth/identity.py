"""Application identities are fetched from 1C, never persisted in Django."""
from dataclasses import dataclass
from uuid import UUID

from rest_framework.exceptions import AuthenticationFailed
from integrations.services.onec_users import OneCUserServiceError

ROLES = frozenset({"user", "mechanic", "admin"})


def native_id_from_profile(profile):
    try:
        return str(UUID(str(profile["onecId"])))
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise OneCUserServiceError(
            "onec_invalid_identity", "1С вернула неверный идентификатор."
        ) from exc


@dataclass(frozen=True)
class NativeUser:
    pk: UUID
    phone: str
    first_name: str
    last_name: str
    patronymic: str
    messenger_user_id: str
    roles: tuple[str, ...]
    birthday: str | None = None

    @property
    def id(self):
        return self.pk

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    @property
    def is_active(self):
        return True

    def has_role(self, role):
        return role in self.roles

    def get_roles(self):
        return list(self.roles)

    def get_full_name(self):
        return " ".join(
            item for item in (self.last_name, self.first_name, self.patronymic)
            if item
        )

    def __str__(self):
        return self.phone


def sync_native_user(profile):
    """Validate a current 1C profile and return an in-memory user."""
    native_id = UUID(native_id_from_profile(profile))
    phone = profile.get("phone")
    roles = profile.get("roles")
    max_id = profile.get("messengerUserId") or ""
    if (
        profile.get("isActive") is not True
        or not isinstance(phone, str) or len(phone) != 11
        or not phone.startswith("7") or not phone.isascii() or not phone.isdigit()
        or not isinstance(roles, list) or not roles
        or any(not isinstance(role, str) for role in roles)
        or not set(roles) <= ROLES or len(roles) != len(set(roles))
        or not isinstance(max_id, str)
    ):
        raise AuthenticationFailed("Учётная запись в 1С недействительна.")
    return NativeUser(
        pk=native_id,
        phone=phone,
        first_name=profile.get("firstName") or "",
        last_name=profile.get("lastName") or "",
        patronymic=profile.get("patronymic") or "",
        messenger_user_id=max_id,
        roles=tuple(roles),
        birthday=profile.get("birthday"),
    )
