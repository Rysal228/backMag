"""Application-user identity resolved from 1C, with no Django ORM record."""
from dataclasses import dataclass
from uuid import UUID

from rest_framework.exceptions import AuthenticationFailed

from integrations.services.onec_users import OneCUserServiceError


VALID_ROLES = frozenset(("user", "mechanic", "admin"))


def native_id_from_profile(profile) -> str:
    try:
        return str(UUID(str(profile["onecId"])))
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise OneCUserServiceError(
            "onec_invalid_response", "1С вернула некорректный UUID пользователя."
        ) from exc


@dataclass(frozen=True)
class OneCUser:
    """DRF request.user for the site; not a Django database model."""

    id: UUID
    phone: str
    roles: tuple[str, ...]
    messenger_user_id: str = ""
    first_name: str = ""
    last_name: str = ""
    patronymic: str = ""
    birthday: str | None = None

    @property
    def pk(self) -> UUID:
        return self.id

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    @property
    def is_active(self) -> bool:
        return True

    def get_roles(self) -> list[str]:
        return list(self.roles)

    def has_role(self, role: str) -> bool:
        return role in self.roles

    def get_full_name(self) -> str:
        return " ".join(
            part for part in (self.last_name, self.first_name, self.patronymic)
            if part
        )

    def __str__(self) -> str:
        return self.get_full_name() or self.phone


def user_from_profile(profile) -> OneCUser:
    """Only a currently active, well-formed 1C account is authenticated."""
    if not isinstance(profile, dict):
        raise OneCUserServiceError(
            "onec_invalid_response", "1С вернула некорректный профиль."
        )
    native_id = native_id_from_profile(profile)
    if profile.get("isActive") is not True:
        raise AuthenticationFailed("Учётная запись неактивна в 1С.")

    phone = profile.get("phone")
    roles = profile.get("roles")
    messenger = profile.get("messengerUserId") or ""
    names = (profile.get("firstName") or "", profile.get("lastName") or "",
             profile.get("patronymic") or "")
    birthday = profile.get("birthday")

    if (
        not isinstance(phone, str) or len(phone) != 11
        or not phone.startswith("7") or not phone.isascii() or not phone.isdigit()
        or not isinstance(roles, list) or not roles
        or any(not isinstance(role, str) for role in roles)
        or len(roles) != len(set(roles))
        or not set(roles).issubset(VALID_ROLES)
        or not isinstance(messenger, str)
        or any(not isinstance(name, str) for name in names)
        or birthday is not None and not isinstance(birthday, str)
    ):
        raise OneCUserServiceError(
            "onec_invalid_response", "1С вернула некорректные данные пользователя."
        )

    return OneCUser(
        id=UUID(native_id), phone=phone, roles=tuple(roles),
        messenger_user_id=messenger,
        first_name=names[0], last_name=names[1], patronymic=names[2],
        birthday=birthday,
    )
