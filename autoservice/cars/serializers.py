from rest_framework import serializers

from cars.models import Car, CarBrand, CarModel


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
    brandName = serializers.CharField(
        source='brand.name',
        read_only=True,
    )
    modelName = serializers.CharField(
        source='model.name',
        read_only=True,
    )

    class Meta:
        model = Car
        fields = [
            'id',
            'brand',
            'brandName',
            'model',
            'modelName',
            'year',
            'vin',
            'plate_number',
            'photo',
        ]
        read_only_fields = [
            'id',
            'brandName',
            'modelName',
        ]

    def validate(self, attrs):
        brand = attrs.get('brand', getattr(self.instance, 'brand', None))
        model = attrs.get('model', getattr(self.instance, 'model', None))

        if brand and model and model.brand_id != brand.id:
            raise serializers.ValidationError({
                'model': 'Выбранная модель не относится к указанной марке.'
            })

        return attrs
