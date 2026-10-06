from django.conf import settings
from django.core import signing
from rest_framework.exceptions import AuthenticationFailed

ROLE_SELECTION_SALT = 'users.role-selection'
ROLE_SELECTION_MAX_AGE = 300


class RoleSelectionService:
    @staticmethod
    def create_token(
        *,
        user,
        auth_method: str,
        messenger_user_id: str | None = None,
        max_verified_phone: str | None = None,
    ) -> str:
        payload = {
            'user_id': str(user.pk),
            'auth_method': auth_method,
        }

        if messenger_user_id is not None:
            payload['messenger_user_id'] = messenger_user_id

        if max_verified_phone is not None:
            payload['max_verified_phone'] = max_verified_phone

        return signing.dumps(
            payload,
            salt=ROLE_SELECTION_SALT,
            compress=True,
        )

    @staticmethod
    def load_token(token: str) -> dict:
        try:
            payload = signing.loads(
                token,
                salt=ROLE_SELECTION_SALT,
                max_age=ROLE_SELECTION_MAX_AGE,
            )
        except signing.BadSignature as exc:
            raise AuthenticationFailed(
                'Сессия выбора роли устарела. Войдите в систему заново.'
            ) from exc

        if not payload.get('user_id') or not payload.get('auth_method'):
            raise AuthenticationFailed(
                'Сессия выбора роли недействительна.'
            )

        return payload
