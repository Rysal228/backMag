from rest_framework import permissions, viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from orders.models import AppointmentSettings, Order, ScheduleBlock, WeekdaySchedule, OrderStatus, WorkStatus, WorkType
from orders.serializers import (
    AppointmentScheduleSerializer,
    OrderSerializer,
    OrderStatusSerializer,
    WorkStatusSerializer,
    WorkTypeSerializer,
)


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
