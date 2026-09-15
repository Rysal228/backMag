from django.contrib.auth import get_user_model
from rest_framework import serializers


class CustomUserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(
        write_only=True,
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

    class Meta:
        model = get_user_model()

        fields = [
            'id',
            'phone',
            'firstName',
            'lastName',
            'patronymic',
            'birthday',
            'password',
        ]

    def create(self, validated_data):
        password = validated_data.pop('password')

        user = super().create(validated_data)
        user.set_password(password)
        user.save()

        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)

        user = super().update(
            instance,
            validated_data,
        )

        if password:
            user.set_password(password)
            user.save()

        return user


class ProfileCustomUserSerializer(serializers.ModelSerializer):
    firstName = serializers.CharField(
        source='first_name',
    )

    lastName = serializers.CharField(
        source='last_name',
    )

    class Meta:
        model = get_user_model()

        fields = [
            'id',
            'username',
            'phone',
            'firstName',
            'lastName',
            'patronymic',
            'birthday',
            'role',
        ]
