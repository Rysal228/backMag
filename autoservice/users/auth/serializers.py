from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenRefreshSerializer


class LoginSerializer(serializers.Serializer):
    phone = serializers.CharField(
        max_length=20,
    )

    password = serializers.CharField(
        write_only=True,
    )


class RegisterSerializer(serializers.Serializer):
    phone = serializers.CharField(
        max_length=20,
    )

    password = serializers.CharField(
        write_only=True,
        min_length=8,
    )

    full_name = serializers.CharField(
        max_length=250,
        required=False,
        allow_blank=True,
    )

    birthday = serializers.DateField(
        required=False,
        allow_null=True,
    )

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


class RefreshSerializer(serializers.Serializer):
    refresh = serializers.CharField(
        write_only=True,
    )


class RefreshTokenSerializer(TokenRefreshSerializer):
    def validate(self, attrs):
        attrs['refresh'] = attrs.pop('refreshToken')

        data = super().validate(attrs)

        return {
            'accessToken': data['access'],
            'refreshToken': data.get('refresh'),
        }