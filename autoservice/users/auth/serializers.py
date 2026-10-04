import re

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

User = get_user_model()


class MaxSessionInvalid(AuthenticationFailed):
    default_code = 'max_session_invalid'
    default_detail = 'MAX-сессия больше не действительна.'


def validate_phone(value: str) -> str:
    phone = value.strip()

    if not re.fullmatch(r'\+7\d{10}', phone):
        raise serializers.ValidationError(
            'Введите корректный номер телефона в формате +7XXXXXXXXXX.'
        )

    return phone


class LoginSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    password = serializers.CharField(write_only=True)

    def validate_phone(self, value):
        return validate_phone(value)


class RegisterSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)

    password = serializers.CharField(
        write_only=True,
        min_length=8,
    )

    firstName = serializers.CharField(
        source='first_name',
        max_length=150,
    )

    lastName = serializers.CharField(
        source='last_name',
        max_length=150,
    )

    patronymic = serializers.CharField(
        max_length=150,
        required=False,
        allow_blank=True,
    )

    birthday = serializers.DateField(
        required=False,
        allow_null=True,
    )

    def validate_phone(self, value):
        return validate_phone(value)

    def validate_password(self, value):
        validate_password(value)

        return value


class PasswordSerializer(serializers.Serializer):
    currentPassword = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
    )
    newPassword = serializers.CharField(
        write_only=True,
        min_length=8,
    )

    def validate_newPassword(self, value):
        validate_password(value)

        return value


class RefreshTokenSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        try:
            refresh_token = RefreshToken(attrs['refresh'])
        except TokenError:
            refresh_token = None

        if refresh_token is not None and refresh_token.get('auth_method') == 'max':
            self._validate_max_binding(refresh_token)

        data = super().validate(attrs)

        return {
            'accessToken': data['access'],
            'refreshToken': data.get('refresh'),
        }

    @staticmethod
    def _validate_max_binding(refresh_token: RefreshToken) -> None:
        user_id = refresh_token.get('user_id')
        messenger_user_id = refresh_token.get('messenger_user_id')
        max_verified_phone = refresh_token.get('max_verified_phone')

        if not user_id or not messenger_user_id or not max_verified_phone:
            raise MaxSessionInvalid()

        user = User.objects.filter(pk=user_id).first()

        if (
            user is None
            or not user.is_active
            or user.messenger_user_id != messenger_user_id
            or user.phone != max_verified_phone
        ):
            raise MaxSessionInvalid()
