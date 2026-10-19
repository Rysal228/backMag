"""Authenticate application JWTs against 1C, without a Django User query."""
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from integrations.services.onec_users import OneCUsersClient, OneCUserServiceError
from users.auth.identity import sync_native_user


def validate_native_claims(token):
    if token.get("auth_method") not in ("password", "max"):
        raise AuthenticationFailed("Недействительный способ авторизации.")
    user_id, role = token.get("user_id"), token.get("active_role")
    if not user_id or not role:
        raise AuthenticationFailed("Недействительная сессия.")
    try:
        profile = OneCUsersClient().get_user_by_onec_id(user_id)
    except OneCUserServiceError as exc:
        if exc.status_code == 404:
            raise AuthenticationFailed("Сессия больше не действительна.") from exc
        raise
    user = sync_native_user(profile)
    if not user.has_role(role):
        raise AuthenticationFailed("Активная роль больше не назначена пользователю.")
    if token["auth_method"] == "max":
        if (
            not token.get("messenger_user_id")
            or token.get("messenger_user_id") != user.messenger_user_id
            or token.get("max_verified_phone") != user.phone
        ):
            raise AuthenticationFailed("MAX-сессия больше не действительна.")
    return user, role


class RoleJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        header = self.get_header(request)
        if header is None:
            return None
        raw = self.get_raw_token(header)
        if raw is None:
            return None
        token = self.get_validated_token(raw)
        user, role = validate_native_claims(token)
        request.active_role = role
        return user, token
