from django.db import transaction
from django.utils import timezone
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


class WorkTypesField(serializers.ListField):
    def __init__(self, **kwargs):
        super().__init__(
            child=serializers.CharField(max_length=100, allow_blank=False),
            allow_empty=False,
            **kwargs,
        )

    def to_internal_value(self, data):
        values = super().to_internal_value(data)
        normalized = []
        seen = set()

        for value in values:
            name = ' '.join(value.split())
            key = name.casefold()

            if key and key not in seen:
                normalized.append(name)
                seen.add(key)

        if not normalized:
            raise serializers.ValidationError('Необходимо указать хотя бы один тип работ.')

        return normalized

    def to_representation(self, value):
        return [work_type.name for work_type in value.all().order_by('name')]


class OrderSerializer(serializers.ModelSerializer):
    orderNumber = serializers.CharField(source='order_number', read_only=True)
    carName = serializers.SerializerMethodField()
    ownerPhone = serializers.SerializerMethodField()
    carYear = serializers.IntegerField(source='car_year_snapshot', read_only=True)
    carVin = serializers.CharField(source='car_vin_snapshot', read_only=True, allow_null=True)
    carPlateNumber = serializers.CharField(source='car_plate_number_snapshot', read_only=True, allow_null=True)
    workTypes = WorkTypesField(source='work_types')
    status = OrderStatusInlineSerializer(read_only=True)
    workStatus = WorkStatusInlineSerializer(source='work_status', read_only=True, allow_null=True)
    appointmentAt = serializers.DateTimeField(source='appointment_at')
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    price = serializers.DecimalField(max_digits=12, decimal_places=2, coerce_to_string=False, read_only=True)

    class Meta:
        model = Order
        fields = (
            'id',
            'orderNumber',
            'car',
            'carName',
            'ownerPhone',
            'carYear',
            'carVin',
            'carPlateNumber',
            'workTypes',
            'status',
            'workStatus',
            'appointmentAt',
            'description',
            'price',
            'createdAt',
        )
        read_only_fields = (
            'id',
            'orderNumber',
            'carName',
            'ownerPhone',
            'carYear',
            'carVin',
            'carPlateNumber',
            'status',
            'workStatus',
            'price',
            'createdAt',
        )

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')

        if not request or request.active_role not in ('mechanic', 'admin'):
            data.pop('ownerPhone', None)

        return data

    def get_carName(self, obj):
        return f'{obj.car_brand_snapshot} {obj.car_model_snapshot}'

    def get_ownerPhone(self, obj):
        return obj.customer.phone

    def validate_car(self, value: Car):
        request = self.context.get('request')
        if request and (
            value.owner_id != request.user.id
            or value.is_archived
        ):
            raise serializers.ValidationError('Выбранный автомобиль недоступен для создания заказа.')
        return value

    def validate_appointmentAt(self, value):
        if not AppointmentAvailabilityService.is_slot_available(
            value,
            exclude_order_id=self.instance.id if self.instance else None,
        ):
            raise serializers.ValidationError('Выбранное время недоступно для записи.')
        return value

    def _resolve_work_types(self, names):
        work_types = []

        for name in names:
            work_type = WorkType.objects.filter(name__iexact=name).first()

            if work_type is None:
                work_type = WorkType.objects.create(name=name)

            work_types.append(work_type)

        return work_types

    @transaction.atomic
    def create(self, validated_data):
        request = self.context['request']
        status = OrderStatus.objects.filter(is_initial=True).first()

        if status is None:
            raise serializers.ValidationError({'status': 'Начальный статус заказа не настроен в системе.'})

        work_type_names = validated_data.pop('work_types')
        work_types = self._resolve_work_types(work_type_names)
        car = validated_data['car']

        order = Order.objects.create(
            order_number=self._generate_order_number(),
            customer=request.user,
            status=status,
            work_type=work_types[0],
            car_brand_snapshot=car.brand.name,
            car_model_snapshot=car.model.name,
            car_year_snapshot=car.year,
            car_vin_snapshot=car.vin,
            car_plate_number_snapshot=car.plate_number,
            **validated_data,
        )
        order.work_types.set(work_types)
        AppointmentAvailabilityService.sync_order_busy_slot(order)

        return order

    @transaction.atomic
    def update(self, instance, validated_data):
        appointment_changed = 'appointment_at' in validated_data
        work_type_names = validated_data.pop('work_types', None)
        order = super().update(instance, validated_data)

        if work_type_names is not None:
            work_types = self._resolve_work_types(work_type_names)
            order.work_types.set(work_types)
            order.work_type = work_types[0]
            order.save(update_fields=('work_type',))

        if appointment_changed:
            AppointmentAvailabilityService.sync_order_busy_slot(order)

        return order

    @staticmethod
    def _generate_order_number():
        import uuid

        return uuid.uuid4().hex[:6].upper()
