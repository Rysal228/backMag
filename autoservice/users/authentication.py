from rest_framework_simplejwt.authentication import JWTAuthentication


class RoleJWTAuthentication(JWTAuthentication):

    def authenticate(self, request):
        result = super().authenticate(request)

        if result is None:
            return None

        user, token = result
        request.active_role = token.get('active_role')

        return user, token
