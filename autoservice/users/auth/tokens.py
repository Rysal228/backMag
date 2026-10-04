from rest_framework_simplejwt.tokens import RefreshToken


def create_auth_tokens(user) -> dict[str, str]:
    refresh = RefreshToken.for_user(user)

    return {
        'accessToken': str(refresh.access_token),
        'refreshToken': str(refresh),
    }


def create_max_auth_tokens(
    user,
    *,
    messenger_user_id: str,
    max_verified_phone: str,
) -> dict[str, str]:
    refresh = RefreshToken.for_user(user)
    refresh['auth_method'] = 'max'
    refresh['messenger_user_id'] = messenger_user_id
    refresh['max_verified_phone'] = max_verified_phone

    return {
        'accessToken': str(refresh.access_token),
        'refreshToken': str(refresh),
    }
