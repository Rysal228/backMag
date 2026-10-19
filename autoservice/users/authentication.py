"""JWT authentication backed by the native 1C catalog UUID."""
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication

from integrations.services.onec_users import OneCUsersClient
from users.auth.identity import sync_native_user


class RoleJWTAuthentication(JWTAuthentication):
    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None

        user, token = result
        current = OneCUsersClient().get_user_by_onec_id(user.pk)
        user = sync_native_user(current)
        role = token.get("active_role")
        if role is None or not user.has_role(role):
            raise AuthenticationFailed(
                "Активная роль больше не назначена пользователю."
            )

        if token.get("auth_method") == "max":
            if (
                not token.get("messenger_user_id")
                or token.get("messenger_user_id") != current.get("messengerUserId")
                or token.get("max_verified_phone") != user.phone
            ):
                raise AuthenticationFailed("MAX-сессия больше не действительна.")

        request.active_role = role
        return user, token
