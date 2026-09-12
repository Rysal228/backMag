import uuid

from rest_framework import serializers

from cars.models import Car, CarModel, CarBrand

class CarBrandSerializer(serializers.ModelSerializer):

    class Meta:
        model = CarBrand
        fields = (
            'id',
            'name',
        )


class CarModelSerializer(serializers.ModelSerializer):

    class Meta:
        model = CarModel
        fields = (
            'id',
            'name',
            'brand',
        )

class CarSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(default=uuid.uuid4)

    class Meta:
        model = Car
        fields = [
            'id',
            'owner',
            'brand',
            'model',
            'year',
            'vin',
            'plate_number',
            'photo'
        ]