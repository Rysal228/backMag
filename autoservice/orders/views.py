from django.db.models import Q
from rest_framework import permissions, serializers, viewsets
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from rest_framework.views import APIView

from orders.models import AppointmentSettings, Order, OrderFilterKey, OrderFilterPermission, ScheduleBlock, WeekdaySchedule, OrderStatus, WorkStatus, WorkType, PaymentStatus
from orders.filters import OrderFilter
from orders.pagination import OrderPagination
from orders.permissions import validate_filter_permissions
from orders.serializers import (
    AppointmentAvailabilitySerializer,
    AppointmentScheduleSerializer,
    OrderSerializer,
    OrderStatusSerializer,
    WorkStatusSerializer,
    WorkTypeSerializer,
    PaymentStatusSerializer,
)
from orders.services.appointment_availability import AppointmentAvailabilityService
from orders.services.order_workflow import OrderWorkflowService


class WorkTypeViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = WorkTypeSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = WorkType.objects.all().order_by('name')
        search = self.request.query_params.get('search', '').strip()

        if search:
            queryset = queryset.filter(name__icontains=search)

        return queryset


class OrderStatusViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = OrderStatus.objects.all().order_by('id')
    serializer_class = OrderStatusSerializer
    permission_classes = [permissions.IsAuthenticated]


class WorkStatusViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = WorkStatus.objects.all().order_by('id')
    serializer_class = WorkStatusSerializer
    permission_classes = [permissions.IsAuthenticated]


class PaymentStatusViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PaymentStatus.objects.all().order_by('id')
    serializer_class = PaymentStatusSerializer
    permission_classes = [permissions.IsAuthenticated]


class AppointmentScheduleView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        settings = AppointmentSettings.objects.first()
        if settings is None:
            settings = AppointmentSettings.objects.create()

        data = {
            'settings': settings,
            'weekdays': WeekdaySchedule.objects.all(),
            'blocks': ScheduleBlock.objects.all(),
        }

        return Response(AppointmentScheduleSerializer(data).data)


class AppointmentAvailabilityView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        target_date = serializers.DateField().to_internal_value(request.query_params.get('date', ''))
        availability = AppointmentAvailabilityService.get_availability(target_date)

        return Response(AppointmentAvailabilitySerializer(availability).data)


class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = OrderPagination
    filter_backends = [DjangoFilterBackend]
    filterset_class = OrderFilter

    def get_queryset(self):
        queryset = Order.objects.select_related(
            'customer',
            'car__brand',
            'car__model',
            'status',
            'work_status',
            'payment_status',
        ).prefetch_related('works__work_type', 'mechanics')

        if self.request.active_role in ('mechanic', 'admin'):
            return queryset.order_by('-created_at')

        return queryset.filter(customer=self.request.user).order_by('-created_at')

    def filter_queryset(self, queryset):
        validate_filter_permissions(self.request)
        return super().filter_queryset(queryset)

    @action(detail=True, methods=['get'], url_path='permissions')
    def permissions(self, request, pk=None):
        order = self.get_object()
        return Response(OrderWorkflowService.permissions(order, request))

    @action(detail=True, methods=['post'], url_path='transition-status')
    def transition_status(self, request, pk=None):
        order = self.get_object()
        status_id = request.data.get('statusId')
        status = OrderStatus.objects.filter(pk=status_id).first()
        if status is None:
            raise serializers.ValidationError({'statusId': 'Статус заказа не найден.'})
        OrderWorkflowService.transition_status(order, request, status)
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=['post'], url_path='transition-work-status')
    def transition_work_status(self, request, pk=None):
        order = self.get_object()
        status_id = request.data.get('statusId')
        status = WorkStatus.objects.filter(pk=status_id).first()
        if status is None:
            raise serializers.ValidationError({'statusId': 'Статус работы не найден.'})
        OrderWorkflowService.transition_work_status(order, request, status)
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=['post'], url_path='payment-status')
    def payment_status(self, request, pk=None):
        order = self.get_object()
        status_id = request.data.get('statusId')
        status = PaymentStatus.objects.filter(pk=status_id).first()
        if status is None:
            raise serializers.ValidationError({'statusId': 'Статус оплаты не найден.'})
        OrderWorkflowService.set_payment_status(order, request, status)
        return Response(self.get_serializer(order).data)

    @action(detail=False, methods=['get'], url_path='filter-permissions')
    def filter_permissions(self, request):
        permissions_map = {key: False for key, _ in OrderFilterKey.choices}

        for filter_permission in OrderFilterPermission.objects.filter(
            role=request.active_role,
            enabled=True,
        ):
            permissions_map[filter_permission.filter_key] = True

        return Response(permissions_map)
