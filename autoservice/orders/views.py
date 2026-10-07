from rest_framework import permissions, serializers, viewsets
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.response import Response
from rest_framework.views import APIView

from orders.models import AppointmentSettings, Order, OrderFilterKey, OrderFilterPermission, ScheduleBlock, WeekdaySchedule, OrderStatus, WorkStatus, WorkType
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
)
from orders.services.appointment_availability import AppointmentAvailabilityService


class WorkTypeViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = WorkType.objects.all().order_by('name')
    serializer_class = WorkTypeSerializer
    permission_classes = [permissions.IsAuthenticated]


class OrderStatusViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = OrderStatus.objects.all().order_by('id')
    serializer_class = OrderStatusSerializer
    permission_classes = [permissions.IsAuthenticated]


class WorkStatusViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = WorkStatus.objects.all().order_by('id')
    serializer_class = WorkStatusSerializer
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
            'work_type',
            'status',
            'work_status',
        )

        if self.request.active_role in ('mechanic', 'admin'):
            return queryset.order_by('-created_at')

        return queryset.filter(customer=self.request.user).order_by('-created_at')

    def filter_queryset(self, queryset):
        validate_filter_permissions(self.request)
        return super().filter_queryset(queryset)

    @action(detail=False, methods=['get'], url_path='filter-permissions')
    def filter_permissions(self, request):
        permissions_map = {key: False for key, _ in OrderFilterKey.choices}

        for filter_permission in OrderFilterPermission.objects.filter(
            role=request.active_role,
            enabled=True,
        ):
            permissions_map[filter_permission.filter_key] = True

        return Response(permissions_map)
