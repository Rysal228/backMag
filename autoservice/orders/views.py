from rest_framework import permissions, serializers, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from orders.models import AppointmentSettings, Order, ScheduleBlock, WeekdaySchedule, OrderStatus, WorkStatus, WorkType
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

    def get_queryset(self):
        return (
            Order.objects
            .filter(customer=self.request.user)
            .select_related('car__brand', 'car__model', 'work_type', 'status', 'work_status')
            .order_by('-created_at')
        )
