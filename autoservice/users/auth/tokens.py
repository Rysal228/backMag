"""JWT tokens keyed by native 1C UUID, without SimpleJWT.for_user()."""
from rest_framework_simplejwt.tokens import RefreshToken
from users.roles import resolve_active_role

TOKEN_VERSION = "native-1c-v1"


def _make_tokens(user, *, role, method, messenger_id=None, phone=None):
    refresh = RefreshToken()
    refresh["user_id"] = str(user.pk)
    refresh["auth_version"] = TOKEN_VERSION
    refresh["auth_method"] = method
    refresh["active_role"] = role
    if method == "max":
        if not messenger_id or not phone:
            raise ValueError("Signed MAX identity is required")
        refresh["messenger_user_id"] = messenger_id
        refresh["max_verified_phone"] = phone
    return {
        "accessToken": str(refresh.access_token),
        "refreshToken": str(refresh),
    }


def create_auth_tokens(user, *, active_role=None):
    return _make_tokens(
        user, role=resolve_active_role(user, active_role), method="password",
    )


def create_max_auth_tokens(
    user, *, messenger_user_id, max_verified_phone, active_role=None,
):
    return _make_tokens(
        user, role=resolve_active_role(user, active_role), method="max",
        messenger_id=messenger_user_id, phone=max_verified_phone,
    )
