from django.db.models import Q
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from cars.models import Car, CarBrand, CarModel
from cars.pagination import CarPagination
from cars.serializers import CarSerializer, CarBrandSerializer, CarModelSerializer
from orders.filters import OrderFilter
from orders.pagination import OrderPagination
from orders.permissions import validate_filter_permissions
from orders.serializers import OrderSerializer
from users.models import UserRole


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
    pagination_class = CarPagination

    def get_queryset(self):
        queryset = Car.objects.filter(is_archived=False)

        if self.request.user.role != UserRole.ADMIN:
            queryset = queryset.filter(owner=self.request.user)

        return queryset.select_related('brand', 'model').order_by(
            'brand__name',
            'model__name',
            'id',
        )

    @action(detail=True, methods=['get'])
    def navigation(self, request, pk=None):
        cars = self.get_queryset()
        current_car = self.get_object()

        previous_car = (
            cars
            .filter(
                Q(brand__name__lt=current_car.brand.name)
                | Q(
                    brand__name=current_car.brand.name,
                    model__name__lt=current_car.model.name,
                )
                | Q(
                    brand__name=current_car.brand.name,
                    model__name=current_car.model.name,
                    id__lt=current_car.id,
                )
            )
            .order_by('-brand__name', '-model__name', '-id')
            .first()
        )

        next_car = (
            cars
            .filter(
                Q(brand__name__gt=current_car.brand.name)
                | Q(
                    brand__name=current_car.brand.name,
                    model__name__gt=current_car.model.name,
                )
                | Q(
                    brand__name=current_car.brand.name,
                    model__name=current_car.model.name,
                    id__gt=current_car.id,
                )
            )
            .order_by('brand__name', 'model__name', 'id')
            .first()
        )

        return Response({
            'previous': CarSerializer(previous_car, context={'request': request}).data if previous_car else None,
            'next': CarSerializer(next_car, context={'request': request}).data if next_car else None,
        })

    @action(detail=True, methods=['get'])
    def orders(self, request, pk=None):
        car = self.get_object()
        validate_filter_permissions(request)

        orders = (
            car.orders
            .select_related('car__brand', 'car__model', 'work_type', 'status', 'work_status')
            .filter(customer=request.user)
            .order_by('-created_at')
        )
        orders = OrderFilter(request.query_params, queryset=orders, request=request).qs

        paginator = OrderPagination()
        page = paginator.paginate_queryset(orders, request, view=self)
        serializer = OrderSerializer(page, many=True, context={'request': request})

        return paginator.get_paginated_response(serializer.data)

    def perform_destroy(self, instance):
        instance.is_archived = True
        instance.save(update_fields=['is_archived'])
