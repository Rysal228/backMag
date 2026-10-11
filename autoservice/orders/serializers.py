from django.db import transaction
from django.db.models import Sum
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied

from cars.models import Car
from orders.services.appointment_availability import AppointmentAvailabilityService
from orders.services.order_workflow import OrderWorkflowService
from users.models import CustomUser, UserRole
from orders.models import (
    AppointmentSettings,
    Order,
    OrderStatus,
    ScheduleBlock,
    WeekdaySchedule,
    WorkStatus,
    WorkType,
    OrderWork,
    PaymentStatus,
)


class OrderWorkSerializer(serializers.ModelSerializer):
    workTypeId = serializers.PrimaryKeyRelatedField(
        source='work_type',
        queryset=WorkType.objects.all(),
        allow_null=True,
        required=False,
    )

    class Meta:
        model = OrderWork
        fields = ('id', 'workTypeId', 'name', 'price')
        read_only_fields = ('id',)


class WorkTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkType
        fields = ('id', 'name')


class OrderStatusSerializer(serializers.ModelSerializer):
    requiresPayment = serializers.BooleanField(source='requires_payment')

    class Meta:
        model = OrderStatus
        fields = ('id', 'code', 'name', 'is_initial', 'requiresPayment')
        read_only_fields = ('id',)


class WorkStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkStatus
        fields = ('id', 'code', 'name')
        read_only_fields = ('id',)


class OrderStatusInlineSerializer(serializers.ModelSerializer):
    requiresPayment = serializers.BooleanField(source='requires_payment', read_only=True)

    class Meta:
        model = OrderStatus
        fields = ('id', 'code', 'name', 'requiresPayment')


class WorkStatusInlineSerializer(serializers.ModelSerializer):
    class Meta:
        model = WorkStatus
        fields = ('id', 'code', 'name')


class PaymentStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentStatus
        fields = ('id', 'code', 'name')
        read_only_fields = ('id',)


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
    mechanics = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=CustomUser.objects.filter(
            role_assignments__role=UserRole.MECHANIC,
        ).distinct(),
        required=False,
    )
    carYear = serializers.IntegerField(source='car_year_snapshot', read_only=True)
    carVin = serializers.CharField(source='car_vin_snapshot', read_only=True, allow_null=True)
    carPlateNumber = serializers.CharField(source='car_plate_number_snapshot', read_only=True, allow_null=True)
    workTypes = WorkTypesField(write_only=True, required=False)
    works = OrderWorkSerializer(many=True, required=False)
    paymentStatus = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    status = OrderStatusInlineSerializer(read_only=True)
    workStatus = WorkStatusInlineSerializer(source='work_status', read_only=True, allow_null=True)
    appointmentAt = serializers.DateTimeField(source='appointment_at')
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    price = serializers.SerializerMethodField()

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
            'works',
            'mechanics',
            'status',
            'workStatus',
            'paymentStatus',
            'permissions',
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
            'paymentStatus',
            'permissions',
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

    def get_price(self, obj):
        return obj.works.aggregate(total=Sum('price'))['total'] or 0

    def get_paymentStatus(self, obj):
        if obj.payment_status is None:
            return None
        return {
            'id': obj.payment_status.id,
            'code': obj.payment_status.code,
            'name': obj.payment_status.name,
        }

    def get_permissions(self, obj):
        return OrderWorkflowService.permissions(obj, self.context['request'])

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

    def validate(self, attrs):
        instance = self.instance
        request = self.context['request']
        if instance is None:
            return attrs
        if 'car' in attrs:
            raise serializers.ValidationError({'car': 'Автомобиль заказа нельзя заменить после его создания.'})
        if 'appointment_at' in attrs and not OrderWorkflowService.can_edit_appointment(instance, request):
            raise serializers.ValidationError({'appointmentAt': 'Изменение даты записи недоступно на текущем этапе заказа.'})
        if ('works' in attrs or 'workTypes' in attrs) and not OrderWorkflowService.can_edit_works(instance, request):
            raise serializers.ValidationError({'works': 'Изменение работ недоступно на текущем этапе заказа.'})
        if 'mechanics' in attrs and not OrderWorkflowService.can_assign_mechanics(instance, request):
            raise serializers.ValidationError({'mechanics': 'Изменение специалистов недоступно на текущем этапе заказа.'})
        if 'description' in attrs and not OrderWorkflowService.can_edit_description(instance, request):
            raise serializers.ValidationError({'description': 'Изменение описания недоступно на текущем этапе заказа.'})
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        request = self.context['request']
        if request.active_role != UserRole.USER:
            raise PermissionDenied('Создавать заказы может только пользователь.')
        status = OrderStatus.objects.filter(is_initial=True).first()
        if status is None:
            raise serializers.ValidationError({'status': 'Начальный статус заказа не настроен в системе.'})
        works = validated_data.pop('works', None)
        work_type_names = validated_data.pop('workTypes', None)
        mechanics = validated_data.pop('mechanics', [])
        car = validated_data['car']
        if works is None:
            if work_type_names is None:
                raise serializers.ValidationError({'works': 'Необходимо указать работы заказа.'})
            works = [{'name': name, 'price': 0} for name in work_type_names]
        work_status = WorkStatus.objects.filter(code=WorkStatus.Code.WAITING_MANAGER_REVIEW).first()
        payment_status = PaymentStatus.objects.filter(code=PaymentStatus.Code.UNPAID).first()
        if work_status is None:
            raise serializers.ValidationError({'workStatus': 'Начальный статус работы не настроен в системе.'})
        if payment_status is None:
            raise serializers.ValidationError({'paymentStatus': 'Начальный статус оплаты не настроен в системе.'})
        order = Order.objects.create(
            order_number=self._generate_order_number(),
            customer=request.user,
            status=status,
            work_status=work_status,
            payment_status=payment_status,
            car_brand_snapshot=car.brand.name,
            car_model_snapshot=car.model.name,
            car_year_snapshot=car.year,
            car_vin_snapshot=car.vin,
            car_plate_number_snapshot=car.plate_number,
            **validated_data,
        )
        self._replace_order_works(order, works)
        order.mechanics.set(mechanics)
        AppointmentAvailabilityService.sync_order_busy_slot(order)
        return order

    @transaction.atomic
    def update(self, instance, validated_data):
        appointment_changed = 'appointment_at' in validated_data
        works = validated_data.pop('works', None)
        work_type_names = validated_data.pop('workTypes', None)
        mechanics = validated_data.pop('mechanics', None)
        order = super().update(instance, validated_data)
        if works is None and work_type_names is not None:
            works = [{'name': name, 'price': 0} for name in work_type_names]
        if works is not None:
            self._replace_order_works(order, works)
        if mechanics is not None:
            order.mechanics.set(mechanics)
        if appointment_changed:
            AppointmentAvailabilityService.sync_order_busy_slot(order)
        return order

    @staticmethod
    def _replace_order_works(order, works):
        prepared = []
        seen_work_types = set()
        for work in works:
            work_type = work.get('work_type')
            name = work.get('name', '').strip()
            if work_type is None:
                work_type = WorkType.objects.filter(name__iexact=name).first()
            if work_type and work_type.pk in seen_work_types:
                raise serializers.ValidationError({'works': f'Тип работы «{work_type.name}» нельзя добавить в заказ дважды.'})
            if work_type:
                seen_work_types.add(work_type.pk)
            prepared.append((work_type, name, work.get('price', 0)))

        OrderWork.objects.filter(order=order).delete()
        for work_type, name, price in prepared:
            OrderWork.objects.create(order=order, work_type=work_type, name=name, price=price)
    @staticmethod
    def _generate_order_number():
        import uuid

        return uuid.uuid4().hex[:6].upper()
