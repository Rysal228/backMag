from rest_framework import serializers


class MaxAuthSerializer(serializers.Serializer):
    initData = serializers.CharField(
        source='init_data',
        write_only=True,
    )

    phone = serializers.CharField(
        max_length=20,
    )

    phoneAuthDate = serializers.CharField(
        source='phone_auth_date',
        write_only=True,
    )

    phoneHash = serializers.CharField(
        source='phone_hash',
        write_only=True,
    )


class MaxCodeRequestSerializer(serializers.Serializer):
    phone = serializers.CharField(
        max_length=20,
    )


class MaxCodeVerifySerializer(serializers.Serializer):
    phone = serializers.CharField(
        max_length=20,
    )
    code = serializers.CharField(
        min_length=6,
        max_length=6,
    )
