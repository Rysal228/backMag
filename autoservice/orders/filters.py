import django_filters
from django.db.models import Q

from orders.models import Order, OrderFilterKey
from orders.permissions import get_allowed_filter_keys


class OrderFilter(django_filters.FilterSet):
    search = django_filters.CharFilter(method='filter_search')
    order_number = django_filters.CharFilter(field_name='order_number', lookup_expr='icontains')
    vin = django_filters.CharFilter(field_name='car_vin_snapshot', lookup_expr='icontains')
    plate_number = django_filters.CharFilter(field_name='car_plate_number_snapshot', lookup_expr='icontains')
    brand = django_filters.NumberFilter(field_name='car__brand_id')
    model = django_filters.NumberFilter(field_name='car__model_id')
    work_type = django_filters.NumberFilter(field_name='work_type_id')
    status = django_filters.NumberFilter(field_name='status_id')
    work_status = django_filters.NumberFilter(field_name='work_status_id')
    date_from = django_filters.DateFilter(field_name='appointment_at', lookup_expr='date__gte')
    date_to = django_filters.DateFilter(field_name='appointment_at', lookup_expr='date__lte')

    class Meta:
        model = Order
        fields = (
            'search',
            'order_number',
            'vin',
            'plate_number',
            'brand',
            'model',
            'work_type',
            'status',
            'work_status',
            'date_from',
            'date_to',
        )

    def filter_search(self, queryset, name, value):
        allowed = get_allowed_filter_keys(self.request.user)
        search_query = Q(
            car_brand_snapshot__icontains=value,
        ) | Q(
            car_model_snapshot__icontains=value,
        ) | Q(
            work_type__name__icontains=value,
        ) | Q(
            description__icontains=value,
        )

        if OrderFilterKey.ORDER_NUMBER in allowed:
            search_query |= Q(order_number__icontains=value)

        if OrderFilterKey.VIN in allowed:
            search_query |= Q(car_vin_snapshot__icontains=value)

        if OrderFilterKey.PLATE_NUMBER in allowed:
            search_query |= Q(car_plate_number_snapshot__icontains=value)

        if self.request.user.role in ('mechanic', 'admin'):
            search_query |= Q(customer__phone__icontains=value)
            search_query |= Q(customer__first_name__icontains=value)
            search_query |= Q(customer__last_name__icontains=value)

        return queryset.filter(search_query).distinct()
