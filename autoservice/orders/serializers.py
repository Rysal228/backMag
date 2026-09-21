from rest_framework import serializers

from cars.models import Car
from orders.services.appointment_availability import AppointmentAvailabilityService
from orders.models import (
    AppointmentSettings,
    Order,
    OrderStatus,
    ScheduleBlock,
    WeekdaySchedule,
    WorkStatus,
    WorkType,
)


class WorkTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkType
        fields = ('id', 'name')


class OrderStatusSerializer(serializers.ModelSerializer):
    requiresPayment = serializers.BooleanField(source='requires_payment')

    class Meta:
        model = OrderStatus
        fields = ('id', 'name', 'appearance', 'is_initial', 'requiresPayment')
        read_only_fields = ('id',)


class WorkStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkStatus
        fields = ('id', 'name', 'appearance')
        read_only_fields = ('id',)


class OrderStatusInlineSerializer(serializers.ModelSerializer):
    requiresPayment = serializers.BooleanField(source='requires_payment', read_only=True)

    class Meta:
        model = OrderStatus
        fields = ('id', 'name', 'appearance', 'requiresPayment')


class WorkStatusInlineSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkStatus
        fields = ('id', 'name', 'appearance')


class AppointmentSettingsSerializer(serializers.ModelSerializer):
    appointmentDuration = serializers.IntegerField(source='appointment_duration')
    slotInterval = serializers.IntegerField(source='slot_interval')

    class Meta:
        model = AppointmentSettings
        fields = ('appointmentDuration', 'slotInterval')


class WeekdayScheduleSerializer(serializers.ModelSerializer):
    weekdayName = serializers.CharField(source='get_weekday_display', read_only=True)
    startTime = serializers.TimeField(source='start_time', format='%H:%M', allow_null=True)
    endTime = serializers.TimeField(source='end_time', format='%H:%M', allow_null=True)

    class Meta:
        model = WeekdaySchedule
        fields = ('weekday', 'weekdayName', 'is_working', 'startTime', 'endTime')


class ScheduleBlockSerializer(serializers.ModelSerializer):
    startTime = serializers.TimeField(source='start_time', format='%H:%M', allow_null=True)
    endTime = serializers.TimeField(source='end_time', format='%H:%M', allow_null=True)

    class Meta:
        model = ScheduleBlock
        fields = ('date', 'startTime', 'endTime')


class AppointmentScheduleSerializer(serializers.Serializer):
    settings = AppointmentSettingsSerializer()
    weekdays = WeekdayScheduleSerializer(many=True)
    blocks = ScheduleBlockSerializer(many=True)


class TimeIntervalSerializer(serializers.Serializer):
    def to_representation(self, instance):
        return {
            'from': instance['from'].strftime('%H:%M'),
            'to': instance['to'].strftime('%H:%M'),
        }


class WorkingHoursSerializer(serializers.Serializer):
    def to_representation(self, instance):
        return {
            'from': instance['from'].strftime('%H:%M'),
            'to': instance['to'].strftime('%H:%M'),
        }


class AppointmentAvailabilitySerializer(serializers.Serializer):
    date = serializers.DateField()
    dayType = serializers.CharField(source='day_type')
    workingHours = WorkingHoursSerializer(source='working_hours', allow_null=True)
    appointmentDuration = serializers.IntegerField(source='appointment_duration')
    slotInterval = serializers.IntegerField(source='slot_interval')
    availableSlots = serializers.ListField(child=serializers.CharField(), source='available_slots')
    busySlots = TimeIntervalSerializer(source='busy_slots', many=True)
    blockedSlots = TimeIntervalSerializer(source='blocked_slots', many=True)


class OrderSerializer(serializers.ModelSerializer):
    orderNumber = serializers.CharField(source='order_number', read_only=True)
    carName = serializers.SerializerMethodField()
    carPlateNumber = serializers.CharField(source='car.plate_number', read_only=True, allow_null=True)
    workType = serializers.PrimaryKeyRelatedField(source='work_type', queryset=WorkType.objects.all())
    workTypeName = serializers.CharField(source='work_type.name', read_only=True)
    status = OrderStatusInlineSerializer(read_only=True)
    workStatus = WorkStatusInlineSerializer(source='work_status', read_only=True, allow_null=True)
    appointmentAt = serializers.DateTimeField(source='appointment_at')
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    price = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=False, read_only=True)

    class Meta:
        model = Order
        fields = ('id', 'orderNumber', 'car', 'carName', 'carPlateNumber', 'workType', 'workTypeName', 'status', 'workStatus', 'appointmentAt', 'description', 'price', 'createdAt')
        read_only_fields = ('id', 'orderNumber', 'carName', 'carPlateNumber', 'workTypeName', 'status', 'workStatus', 'price', 'createdAt')

    def get_carName(self, obj):
        return f'{obj.car.brand.name} {obj.car.model.name}'

    def validate_car(self, value: Car):
        request = self.context.get('request')
        if request and value.owner_id != request.user.id:
            raise serializers.ValidationError('Выбранный автомобиль вам не принадлежит.')
        return value

    def validate_appointmentAt(self, value):
        if not AppointmentAvailabilityService.is_slot_available(
            value,
            exclude_order_id=self.instance.id if self.instance else None,
        ):
            raise serializers.ValidationError('Выбранное время недоступно для записи.')
        return value

    def create(self, validated_data):
        request = self.context['request']
        status = OrderStatus.objects.filter(is_initial=True).first()

        if status is None:
            raise serializers.ValidationError({'status': 'Начальный статус заказа не настроен в системе.'})

        order = Order.objects.create(
            order_number=self._generate_order_number(),
            customer=request.user,
            status=status,
            **validated_data,
        )
        AppointmentAvailabilityService.sync_order_busy_slot(order)
        return order

    def update(self, instance, validated_data):
        appointment_changed = 'appointment_at' in validated_data
        order = super().update(instance, validated_data)

        if appointment_changed:
            AppointmentAvailabilityService.sync_order_busy_slot(order)

        return order

    @staticmethod
    def _generate_order_number():
        import uuid
        return uuid.uuid4().hex[:8]
