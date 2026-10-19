"""Application authentication via signed JWT and the current 1C identity."""
from rest_framework_simplejwt.authentication import JWTAuthentication

from users.auth.tokens import validate_token_subject


class RoleJWTAuthentication(JWTAuthentication):
    def get_user(self, validated_token):
        # JWTAuthentication.authenticate() invokes this method. No ORM query.
        return validate_token_subject(validated_token)

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        user, token = result
        request.active_role = token['active_role']
        return user, token
