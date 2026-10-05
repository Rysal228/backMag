import re

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from cars.models import Car, CarBrand, CarModel, CarOwnership


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
    hasOrders = serializers.SerializerMethodField()
    vin = serializers.CharField(
        max_length=64,
        required=False,
        allow_blank=True,
        allow_null=True,
        validators=[],
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
            'hasOrders',
        ]
        read_only_fields = [
            'id',
            'brandName',
            'modelName',
            'hasOrders',
        ]

    def get_hasOrders(self, obj):
        return obj.orders.exists()

    def validate(self, attrs):
        brand = attrs.get('brand', getattr(self.instance, 'brand', None))
        model = attrs.get('model', getattr(self.instance, 'model', None))

        if brand and model and model.brand_id != brand.id:
            raise serializers.ValidationError({
                'model': 'Выбранная модель не относится к указанной марке.'
            })

        if self.instance and self.instance.orders.exists():
            protected_fields = ('brand', 'model', 'year', 'vin')

            changed_fields = [
                field
                for field in protected_fields
                if field in attrs and not self._same_value(
                    field,
                    getattr(self.instance, field),
                    attrs[field],
                )
            ]

            if changed_fields:
                raise serializers.ValidationError({
                    field: 'Это поле нельзя изменять, потому что у автомобиля уже есть заказы.'
                    for field in changed_fields
                })

        return attrs

    @staticmethod
    def _same_value(field, current, new):
        if field == 'vin':
            current = (current or '').strip().upper()
            new = (new or '').strip().upper()

        return current == new

    def validate_vin(self, value):
        if not value:
            return None

        value = value.strip().upper()

        if not value:
            return None

        if not re.fullmatch(r'[A-HJ-NPR-Z0-9]{17}', value):
            raise serializers.ValidationError(
                'VIN должен содержать 17 символов: латинские буквы и цифры, без I, O и Q.'
            )

        if self.instance and Car.objects.filter(vin=value).exclude(pk=self.instance.pk).exists():
            raise serializers.ValidationError('Автомобиль с таким VIN уже зарегистрирован.')

        return value

    @transaction.atomic
    def create(self, validated_data):
        owner = self.context['request'].user
        vin = validated_data.get('vin')

        if not vin:
            car = Car.objects.create(owner=owner, **validated_data)
            CarOwnership.objects.create(car=car, owner=owner)
            return car

        car = (
            Car.objects
            .select_for_update()
            .select_related('model')
            .filter(vin=vin)
            .first()
        )

        if car is None:
            car = Car.objects.create(owner=owner, **validated_data)
            CarOwnership.objects.create(car=car, owner=owner)
            return car

        if car.owner_id == owner.id:
            if not car.is_archived:
                raise serializers.ValidationError({
                    'vin': 'Автомобиль с таким VIN уже добавлен в ваш аккаунт.'
                })

            self._validate_identity_data(car, validated_data)

            for field, value in validated_data.items():
                setattr(car, field, value)

            car.is_archived = False
            car.save()
            return car

        if not car.is_archived:
            raise serializers.ValidationError({
                'vin': 'Автомобиль с таким VIN уже зарегистрирован.'
            })

        self._validate_identity_data(car, validated_data)

        current_ownership = (
            car.ownership_history
            .select_for_update()
            .filter(ended_at__isnull=True)
            .first()
        )

        if current_ownership is not None:
            current_ownership.ended_at = timezone.now()
            current_ownership.save(update_fields=('ended_at',))

        for field, value in validated_data.items():
            setattr(car, field, value)

        car.owner = owner
        car.is_archived = False
        car.save()

        CarOwnership.objects.create(
            car=car,
            owner=owner,
        )

        return car

    @staticmethod
    def _validate_identity_data(car, validated_data):
        if (
            validated_data['brand'].id != car.brand_id
            or validated_data['model'].id != car.model_id
            or validated_data['year'] != car.year
        ):
            raise serializers.ValidationError({
                'vin': 'Основные данные автомобиля не совпадают с данными, сохранёнными для этого VIN.'
            })
