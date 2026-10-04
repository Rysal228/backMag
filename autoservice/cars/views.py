from rest_framework import permissions, status, viewsets

from cars.models import Car, CarBrand, CarModel
from cars.serializers import CarSerializer, CarBrandSerializer, CarModelSerializer
from orders.serializers import OrderSerializer
from rest_framework.decorators import action
from rest_framework.response import Response


class CarBrandViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = CarBrand.objects.all().order_by('name')
    serializer_class = CarBrandSerializer
    permission_classes = [permissions.IsAuthenticated]


class CarModelViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CarModelSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = CarModel.objects.select_related('brand').all().order_by('name')
        brand_id = self.request.query_params.get('brand')

        if brand_id:
            queryset = queryset.filter(brand_id=brand_id)

        return queryset


class CarViewSet(viewsets.ModelViewSet):
    serializer_class = CarSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return (
            Car.objects
            .filter(owner=self.request.user)
            .select_related('brand', 'model')
            .order_by('brand__name', 'model__name')
        )

    @action(detail=True, methods=['get'])
    def orders(self, request, pk=None):
        car = self.get_object()
        orders = (
            car.orders
            .select_related('car__brand', 'car__model', 'work_type', 'status', 'work_status')
            .order_by('-created_at')
        )

        serializer = OrderSerializer(orders, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
