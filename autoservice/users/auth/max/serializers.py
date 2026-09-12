from rest_framework import serializers


class MaxAuthSerializer(serializers.Serializer):
    init_data = serializers.CharField(
        write_only=True,
    )

    phone = serializers.CharField(
        max_length=20,
    )

    phone_auth_date = serializers.CharField(
        write_only=True,
    )

    phone_hash = serializers.CharField(
        write_only=True,
    )