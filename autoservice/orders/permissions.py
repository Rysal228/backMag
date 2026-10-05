from rest_framework.exceptions import PermissionDenied

from orders.models import OrderFilterKey, OrderFilterPermission


QUERY_TO_FILTER = {
    'search': OrderFilterKey.SEARCH,
    'order_number': OrderFilterKey.ORDER_NUMBER,
    'vin': OrderFilterKey.VIN,
    'plate_number': OrderFilterKey.PLATE_NUMBER,
    'brand': OrderFilterKey.BRAND,
    'model': OrderFilterKey.MODEL,
    'work_type': OrderFilterKey.WORK_TYPE,
    'status': OrderFilterKey.STATUS,
    'work_status': OrderFilterKey.WORK_STATUS,
    'date_from': OrderFilterKey.DATE_RANGE,
    'date_to': OrderFilterKey.DATE_RANGE,
}


def get_allowed_filter_keys(user):
    return set(
        OrderFilterPermission.objects.filter(
            role=user.role,
            enabled=True,
        ).values_list('filter_key', flat=True)
    )


def validate_filter_permissions(request):
    allowed = get_allowed_filter_keys(request.user)
    denied = {
        query_key
        for query_key, filter_key in QUERY_TO_FILTER.items()
        if request.query_params.get(query_key) not in (None, '')
        and filter_key not in allowed
    }

    if denied:
        raise PermissionDenied(
            f'Фильтры недоступны для вашей роли: {", ".join(sorted(denied))}.'
        )
