from rest_framework_simplejwt.authentication import JWTAuthentication


class RoleJWTAuthentication(JWTAuthentication):

    def authenticate(self, request):
        result = super().authenticate(request)

        if result is None:
            return None

        user, token = result
        request.active_role = token.get('active_role')

        if request.active_role is None:
            return user, token

        if not user.has_role(request.active_role):
            from rest_framework.exceptions import AuthenticationFailed

            raise AuthenticationFailed(
                'Активная роль больше не назначена пользователю.'
            )

        return user, token
