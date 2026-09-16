import re

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from django.contrib.auth.password_validation import validate_password

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
    password = serializers.CharField(
        write_only=True,
        min_length=8,
    )

    def validate_password(self, value):
        validate_password(value)

        return value

class RefreshTokenSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)

        return {
            'accessToken': data['access'],
            'refreshToken': data.get('refresh'),
        }