from rest_framework_simplejwt.tokens import RefreshToken


def create_auth_tokens(user) -> dict[str, str]:
    refresh = RefreshToken.for_user(user)

    return {
        'accessToken': str(refresh.access_token),
        'refreshToken': str(refresh),
    }