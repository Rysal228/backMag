from rest_framework_simplejwt.tokens import RefreshToken

from users.roles import resolve_active_role


def create_auth_tokens(
    user,
    *,
    active_role: str | None = None,
) -> dict[str, str]:
    active_role = resolve_active_role(user, active_role)

    refresh = RefreshToken.for_user(user)
    refresh['auth_method'] = 'password'
    refresh['active_role'] = active_role

    return {
        'accessToken': str(refresh.access_token),
        'refreshToken': str(refresh),
    }


def create_max_auth_tokens(
    user,
    *,
    messenger_user_id: str,
    max_verified_phone: str,
    active_role: str | None = None,
) -> dict[str, str]:
    active_role = resolve_active_role(user, active_role)

    refresh = RefreshToken.for_user(user)
    refresh['auth_method'] = 'max'
    refresh['active_role'] = active_role
    refresh['messenger_user_id'] = messenger_user_id
    refresh['max_verified_phone'] = max_verified_phone

    return {
        'accessToken': str(refresh.access_token),
        'refreshToken': str(refresh),
    }
