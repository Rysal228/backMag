from django.contrib.auth import authenticate, get_user_model
from rest_framework.exceptions import AuthenticationFailed, ValidationError

from .tokens import create_auth_tokens

User = get_user_model()


class AuthService:
    @staticmethod
    def login(*, phone: str, password: str) -> dict[str, str]:
        phone = PhoneNormalizer.normalize(phone)

        user = authenticate(
            username=phone,
            password=password,
        )

        if user is None:
            raise AuthenticationFailed(
                'Invalid phone or password.'
            )

        if not user.is_active:
            raise AuthenticationFailed(
                'User is inactive.'
            )

        return create_auth_tokens(user)

    @staticmethod
    def register(
        *,
        phone: str,
        password: str,
        first_name: str,
        last_name: str,
        patronymic: str = '',
        birthday=None,
    ) -> dict[str, str]:
        phone = PhoneNormalizer.normalize(phone)

        if User.objects.filter(phone=phone).exists():
            raise ValidationError({
                'phone': 'User with this phone already exists.',
            })

        user = User.objects.create_user(
            phone=phone,
            password=password,
            first_name=first_name,
            last_name=last_name,
            patronymic=patronymic,
            birthday=birthday,
        )

        return create_auth_tokens(user)


class PhoneNormalizer:

    @staticmethod
    def normalize(phone: str) -> str:
        phone = phone.strip()

        if phone.startswith('+'):
            phone = phone[1:]

        if not phone.isdigit():
            raise ValidationError({
                'phone': 'Invalid phone number.',
            })

        return phone