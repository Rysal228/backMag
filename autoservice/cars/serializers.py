import re

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

    def validate_vin(self, value):
        if not value:
            return value

        value = value.strip().upper()

        if not re.fullmatch(r'[A-HJ-NPR-Z0-9]{17}', value):
            raise serializers.ValidationError(
                'VIN должен содержать 17 символов: латинские буквы и цифры, без I, O и Q.'
            )

        return value

    def create(self, validated_data):
        request = self.context['request']
        owner = request.user
        vin = validated_data.get('vin')

        if vin:
            archived_car = (
                Car.objects
                .filter(owner=owner, vin=vin, is_archived=True)
                .select_related('model')
                .first()
            )

            if archived_car:
                if (
                    validated_data['brand'].id != archived_car.brand_id
                    or validated_data['model'].id != archived_car.model_id
                ):
                    raise serializers.ValidationError({
                        'vin': 'Автомобиль с таким VIN уже существует в вашей истории, но марка или модель не совпадает.'
                    })

                for field, value in validated_data.items():
                    setattr(archived_car, field, value)

                archived_car.is_archived = False
                archived_car.save()
                return archived_car

        return Car.objects.create(owner=owner, **validated_data)    @transaction.atomic
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

        if (
            validated_data['brand'].id != car.brand_id
            or validated_data['model'].id != car.model_id
            or validated_data['year'] != car.year
        ):
            raise serializers.ValidationError({
                'vin': 'Основные данные автомобиля не совпадают с данными, сохранёнными для этого VIN.'
            })

        if car.owner_id == owner.id:
            if not car.is_archived:
                raise serializers.ValidationError({
                    'vin': 'Автомобиль с таким VIN уже добавлен в ваш аккаунт.'
                })

            for field, value in validated_data.items():
                setattr(car, field, value)

            car.is_archived = False
            car.save()
            return car

        if not car.is_archived:
            raise serializers.ValidationError({
                'vin': 'Автомобиль с таким VIN уже зарегистрирован.'
            })

        from django.utils import timezone

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
        CarOwnership.objects.create(car=car, owner=owner)

        return car
