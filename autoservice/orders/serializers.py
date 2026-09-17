from django.utils import timezone
from rest_framework import serializers

from cars.models import Car
from orders.models import Order, OrderStatus, WorkType


class WorkTypeSerializer(serializers.ModelSerializer):

    class Meta:
        model = WorkType
        fields = (
            'id',
            'name',
        )


class OrderStatusSerializer(serializers.ModelSerializer):

    class Meta:
        model = OrderStatus
        fields = (
            'id',
            'name',
        )


class OrderSerializer(serializers.ModelSerializer):
    orderNumber = serializers.CharField(source='order_number', read_only=True)
    carName = serializers.SerializerMethodField()
    carPlateNumber = serializers.CharField(source='car.plate_number', read_only=True, allow_null=True)
    workTypeName = serializers.CharField(source='work_type.name', read_only=True)
    statusName = serializers.CharField(source='status.name', read_only=True)
    appointmentAt = serializers.DateTimeField(source='appointment_at')
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)

    class Meta:
        model = Order
        fields = (
            'id',
            'orderNumber',
            'car',
            'carName',
            'carPlateNumber',
            'work_type',
            'workTypeName',
            'statusName',
            'appointmentAt',
            'description',
            'price',
            'createdAt',
        )
        read_only_fields = (
            'id',
            'orderNumber',
            'carName',
            'carPlateNumber',
            'workTypeName',
            'statusName',
            'price',
            'createdAt',
        )

    def get_carName(self, obj):
        return f'{obj.car.brand.name} {obj.car.model.name}'

    def validate_car(self, value: Car):
        request = self.context.get('request')
        if request and value.owner_id != request.user.id:
            raise serializers.ValidationError(
                'Выбранный автомобиль вам не принадлежит.'
            )
        return value

    def validate_appointmentAt(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError(
                'Дата и время записи должны быть в будущем.'
            )
        return value

    def create(self, validated_data):
        request = self.context['request']
        status = OrderStatus.objects.filter(name='На рассмотрении').first()

        if status is None:
            raise serializers.ValidationError({
                'status': 'Статус «На рассмотрении» не настроен в системе.'
            })

        return Order.objects.create(
            order_number=self._generate_order_number(),
            customer=request.user,
            status=status,
            **validated_data,
        )

    @staticmethod
    def _generate_order_number():
        import uuid

        return uuid.uuid4().hex[:8]
