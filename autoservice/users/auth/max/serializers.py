from rest_framework import serializers


class MaxAuthSerializer(serializers.Serializer):
    initData = serializers.CharField(
        source='init_data',
        write_only=True,
    )
    phone = serializers.CharField(max_length=20, required=False)
    forceContact = serializers.BooleanField(
        source='force_contact',
        required=False,
        default=False,
        write_only=True,
    )
    phoneAuthDate = serializers.CharField(
        source='phone_auth_date',
        write_only=True,
        required=False,
    )
    phoneHash = serializers.CharField(
        source='phone_hash',
        write_only=True,
        required=False,
    )

    def validate(self, attrs):
        fields = ('phone', 'phone_auth_date', 'phone_hash')
        supplied = [field in attrs for field in fields]
        if any(supplied) and not all(supplied):
            raise serializers.ValidationError(
                'Для авторизации по контакту необходимо передать все данные телефона.',
            )
        return attrs


class MaxCodeRequestSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)


class MaxCodeVerifySerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    code = serializers.CharField(min_length=6, max_length=6)
