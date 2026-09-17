from rest_framework import permissions, viewsets

from orders.models import Order, OrderStatus, WorkStatus, WorkType
from orders.serializers import OrderSerializer, OrderStatusSerializer, WorkStatusSerializer, WorkTypeSerializer


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
