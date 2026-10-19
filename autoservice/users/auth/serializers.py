import re

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from .token_rotation import rotate_refresh


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
    role = serializers.CharField(required=False, allow_blank=False)

    def validate_phone(self, value):
        return validate_phone(value)


class RoleSerializer(serializers.Serializer):
    role = serializers.CharField()


class RegisterSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)

    password = serializers.CharField(
        write_only=True,
        min_length=8,
        max_length=128,
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
        max_length=128,
    )
    newPassword = serializers.CharField(
        write_only=True,
        min_length=8,
        max_length=128,
    )

    def validate_newPassword(self, value):
        validate_password(value)

        return value


class RefreshTokenSerializer(serializers.Serializer):
    refresh = serializers.CharField(write_only=True)

    def validate(self, attrs):
        return rotate_refresh(attrs["refresh"])
