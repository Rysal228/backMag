from django.contrib.auth import get_user_model
from rest_framework import serializers


class CustomUserSerializer(serializers.ModelSerializer):
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
        ]
