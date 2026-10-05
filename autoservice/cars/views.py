from rest_framework import permissions, viewsets
from rest_framework.decorators import action

from cars.models import Car, CarBrand, CarModel
from cars.serializers import CarSerializer, CarBrandSerializer, CarModelSerializer
from orders.pagination import OrderPagination
from orders.serializers import OrderSerializer


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
            .filter(owner=self.request.user, is_archived=False)
            .select_related('brand', 'model')
            .order_by('brand__name', 'model__name')
        )

    @action(detail=True, methods=['get'])
    def orders(self, request, pk=None):
        car = self.get_object()
        orders = (
            car.orders
            .select_related('car__brand', 'car__model', 'work_type', 'status', 'work_status')
            .filter(customer=request.user)
            .order_by('-created_at')
        )

        paginator = OrderPagination()
        page = paginator.paginate_queryset(orders, request, view=self)
        serializer = OrderSerializer(page, many=True, context={'request': request})

        return paginator.get_paginated_response(serializer.data)

    def perform_destroy(self, instance):
        instance.is_archived = True
        instance.save(update_fields=['is_archived'])
