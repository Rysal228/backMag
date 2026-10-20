"""HTTP serialization only. Vehicle models are authoritative in 1C."""
import re
from datetime import date
from rest_framework import serializers


class CarBrandSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)


class CarModelSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    brand = serializers.UUIDField(read_only=True)


class CarSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    brand = serializers.UUIDField(read_only=True)
    brandName = serializers.CharField(read_only=True)
    model = serializers.UUIDField(read_only=True)
    modelName = serializers.CharField(read_only=True)
    ownerName = serializers.CharField(read_only=True)
    ownerPhone = serializers.CharField(read_only=True)
    year = serializers.IntegerField(read_only=True)
    vin = serializers.CharField(read_only=True, allow_blank=True, allow_null=True)
    plate_number = serializers.CharField(read_only=True, allow_blank=True, allow_null=True)
    photo = serializers.CharField(read_only=True, allow_blank=True, allow_null=True)
    hasOrders = serializers.BooleanField(read_only=True)
    status = serializers.CharField(read_only=True)


class CarWriteSerializer(serializers.Serializer):
    brand = serializers.UUIDField(required=True)
    model = serializers.UUIDField(required=True)
    year = serializers.IntegerField(min_value=1886, max_value=date.today().year + 1)
    vin = serializers.CharField(
        max_length=64, required=False, allow_blank=True, allow_null=True,
    )
    plate_number = serializers.CharField(
        max_length=20, required=False, allow_blank=True, allow_null=True,
    )

    def validate_vin(self, value):
        value = (value or "").strip().upper()
        if value and not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", value):
            raise serializers.ValidationError(
                "VIN должен содержать 17 символов: латинские буквы и цифры, без I, O и Q."
            )
        return value
