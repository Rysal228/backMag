from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.hashers import check_password
from django.contrib.auth.password_validation import validate_password
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
                'Неверный номер телефона или пароль.'
            )

        if not user.is_active:
            raise AuthenticationFailed(
                'Пользователь деактивирован.'
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

    @staticmethod
    def set_password(
        *,
        user,
        current_password: str | None,
        new_password: str,
    ) -> None:
        if user.has_usable_password():
            if not current_password or not check_password(
                current_password,
                user.password,
            ):
                raise ValidationError({
                    'currentPassword': 'Неверный текущий пароль.'
                })

        validate_password(new_password, user)

        user.set_password(new_password)
        user.save(update_fields=['password'])


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
