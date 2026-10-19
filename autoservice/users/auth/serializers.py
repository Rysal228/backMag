import re

from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.tokens import RefreshToken, TokenError


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


class RefreshTokenSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        try:
            refresh_token = RefreshToken(attrs["refresh"])
        except TokenError:
            refresh_token = None

        if refresh_token is not None:
            from integrations.services.onec_users import OneCUsersClient
            from .identity import sync_native_user

            user_id = refresh_token.get("user_id")
            role = refresh_token.get("active_role")
            if not user_id or not role:
                raise AuthenticationFailed(
                    "Сессия устарела. Войдите в систему заново."
                )
            profile = OneCUsersClient().get_user_by_onec_id(user_id)
            user = sync_native_user(profile)
            if not user.has_role(role):
                raise AuthenticationFailed(
                    "Активная роль больше не назначена пользователю."
                )

            if refresh_token.get("auth_method") == "max":
                messenger = refresh_token.get("messenger_user_id", "")
                phone = refresh_token.get("max_verified_phone", "")
                if (
                    not messenger
                    or messenger != profile.get("messengerUserId")
                    or phone != user.phone
                ):
                    raise MaxSessionInvalid()
                from .max.services import MaxAuthService
                try:
                    MaxAuthService.validate_current_binding(
                        user=user, messenger_user_id=messenger,
                        max_verified_phone=phone,
                    )
                except AuthenticationFailed as exc:
                    raise MaxSessionInvalid() from exc

        data = super().validate(attrs)
        return {
            "accessToken": data["access"],
            "refreshToken": data.get("refresh"),
        }
