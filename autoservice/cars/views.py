from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import permissions, viewsets
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.decorators import action
from rest_framework.response import Response

from cars.models import Car, CarBrand, CarModel
from cars.pagination import CarPagination
from cars.serializers import CarSerializer, CarBrandSerializer, CarModelSerializer
from orders.filters import OrderFilter
from orders.pagination import OrderPagination
from orders.permissions import validate_filter_permissions
from orders.serializers import OrderSerializer
from users.auth.services import PhoneNormalizer
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
        queryset = Car.objects.all()
        active_role = self.request.active_role
        status = self.request.query_params.get('status')

        if active_role == UserRole.USER:
            queryset = queryset.filter(owner=self.request.user)
        elif active_role == UserRole.MECHANIC:
            queryset = queryset.filter(
                orders__mechanics=self.request.user,
            ).distinct()

        if status not in {'active', 'archived', 'all'}:
            status = 'active' if active_role in {UserRole.USER, UserRole.MECHANIC} else 'all'

        if status == 'active':
            queryset = queryset.filter(is_archived=False)
        elif status == 'archived':
            queryset = queryset.filter(is_archived=True)

        if active_role in {UserRole.MECHANIC, UserRole.ADMIN}:
            owner_phone = self.request.query_params.get('owner_phone')
            if owner_phone:
                owner_phone = PhoneNormalizer.normalize(owner_phone)
                queryset = queryset.filter(owner__phone__icontains=owner_phone)

        brand_id = self.request.query_params.get('brand')
        if brand_id:
            queryset = queryset.filter(brand_id=brand_id)

        model_id = self.request.query_params.get('model')
        if model_id:
            queryset = queryset.filter(model_id=model_id)

        year = self.request.query_params.get('year')
        if year:
            try:
                queryset = queryset.filter(year=int(year))
            except ValueError:
                pass

        vin = self.request.query_params.get('vin')
        if vin:
            queryset = queryset.filter(vin__icontains=vin.strip())

        plate_number = self.request.query_params.get('plate_number')
        if plate_number:
            queryset = queryset.filter(plate_number__icontains=plate_number.strip())

        return queryset.select_related('owner', 'brand', 'model').order_by(
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
        if request.active_role == UserRole.USER:
            car = get_object_or_404(Car, pk=pk, owner=request.user)
        else:
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

    @action(detail=True, methods=['post'])
    def restore(self, request, pk=None):
        if request.active_role != UserRole.USER:
            raise PermissionDenied('Только пользователь может восстанавливать автомобиль.')

        car = get_object_or_404(Car, pk=pk, owner=request.user)

        if not car.is_archived:
            raise ValidationError({'detail': 'Автомобиль уже активен.'})

        car.is_archived = False
        car.save(update_fields=['is_archived'])

        return Response(CarSerializer(car, context={'request': request}).data)

    def create(self, request, *args, **kwargs):
        if request.active_role != UserRole.USER:
            raise PermissionDenied('Только пользователь может добавлять автомобили.')

        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        self._ensure_owner_can_manage()
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        self._ensure_owner_can_manage()
        return super().partial_update(request, *args, **kwargs)

    def perform_destroy(self, instance):
        self._ensure_owner_can_manage(instance)
        instance.is_archived = True
        instance.save(update_fields=['is_archived'])

    def _ensure_owner_can_manage(self, instance=None):
        if self.request.active_role != UserRole.USER:
            raise PermissionDenied(
                'Только владелец автомобиля может изменять или удалять его.'
            )

        instance = instance or self.get_object()
        if instance.owner_id != self.request.user.id:
            raise PermissionDenied(
                'Только владелец автомобиля может изменять или удалять его.'
            )
