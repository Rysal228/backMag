"""Django HTTP facade: all order records, catalogs and schedule live in 1C."""
from datetime import timedelta
from uuid import UUID

from django.utils import timezone
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.services.onec_orders import OneCOrdersClient
from orders.models import OrderFilterKey, OrderFilterPermission, StatisticsPeriodOption
from orders.pagination import OrderPagination
from orders.permissions import validate_filter_permissions
from users.models import UserRole


def _actor(request):
    return request.user.id, request.active_role


def _uuid(value, field):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationError({field: "Некорректный идентификатор справочника 1С."}) from exc


def _order_payload(request):
    """Do not forward unknown or server-owned fields to the authoritative 1C API."""
    if not isinstance(request.data, dict):
        raise ValidationError("Ожидается JSON-объект заказа.")
    writable = {"car", "appointmentAt", "description", "works", "mechanics"}
    forbidden = set(request.data) - writable
    if forbidden:
        raise ValidationError({key: "Недоступное поле заказа." for key in sorted(forbidden)})
    payload = dict(request.data)
    if "car" in payload:
        payload["car"] = _uuid(payload["car"], "car")
    if "appointmentAt" in payload:
        value = serializers.DateTimeField().run_validation(payload["appointmentAt"])
        # 1C uses local workshop +07, not Django's UTC storage representation.
        payload["appointmentAt"] = timezone.localtime(value).isoformat(timespec="seconds")
    if "description" in payload:
        payload["description"] = serializers.CharField(allow_blank=True).run_validation(
            payload["description"]
        )
    if "mechanics" in payload:
        if not isinstance(payload["mechanics"], list):
            raise ValidationError({"mechanics": "Ожидается список специалистов."})
        payload["mechanics"] = [_uuid(x, "mechanics") for x in payload["mechanics"]]
    if "works" in payload:
        if not isinstance(payload["works"], list):
            raise ValidationError({"works": "Ожидается список работ."})
        result = []
        for work in payload["works"]:
            if not isinstance(work, dict) or set(work) - {"id", "workTypeId", "price"}:
                raise ValidationError({"works": "Разрешён только выбор вида работ из 1С."})
            prepared = {"workTypeId": _uuid(work.get("workTypeId"), "workTypeId")}
            if "id" in work and work["id"] is not None:
                prepared["id"] = _uuid(work["id"], "id")
            if "price" in work:
                prepared["price"] = str(serializers.DecimalField(max_digits=12, decimal_places=2,
                        min_value=0).run_validation(work["price"]))
            result.append(prepared)
        payload["works"] = result
    return payload


def _order_filters(request):
    validate_filter_permissions(request)
    permitted = OneCOrdersClient.LIST_FILTERS - {"car"}
    unknown = set(request.query_params) - permitted - {"page", "page_size", "format"}
    if unknown:
        raise ValidationError({
            key: "Неизвестный параметр фильтра." for key in sorted(unknown)
        })
    return {key: request.query_params[key] for key in permitted
            if request.query_params.get(key) not in (None, "")}


def _list_response(records, request, view):
    paginator = OrderPagination()
    page = paginator.paginate_queryset(records, request, view=view)
    return paginator.get_paginated_response(page)


class _CatalogViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]
    catalog_method = None

    def list(self, request):
        client = OneCOrdersClient()
        if self.catalog_method == "work_types":
            data = client.work_types(*_actor(request), search=request.query_params.get("search", ""))
        else:
            data = getattr(client, self.catalog_method)(*_actor(request))
        return Response(data)

    def retrieve(self, request, pk=None):
        identifier = _uuid(pk, "id")
        client = OneCOrdersClient()
        records = (client.work_types(*_actor(request))
                   if self.catalog_method == "work_types"
                   else getattr(client, self.catalog_method)(*_actor(request)))
        record = next((x for x in records if x.get("id") == identifier), None)
        if record is None:
            from rest_framework.exceptions import NotFound
            raise NotFound("Элемент справочника не найден.")
        return Response(record)


class WorkTypeViewSet(_CatalogViewSet):
    catalog_method = "work_types"


class OrderStatusViewSet(_CatalogViewSet):
    catalog_method = "order_statuses"


class WorkStatusViewSet(_CatalogViewSet):
    catalog_method = "work_statuses"


class PaymentStatusViewSet(_CatalogViewSet):
    catalog_method = "payment_statuses"


class AppointmentScheduleView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        return Response(OneCOrdersClient().schedule(*_actor(request)))


class AppointmentAvailabilityView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        day = serializers.DateField().run_validation(request.query_params.get("date"))
        return Response(OneCOrdersClient().availability(*_actor(request), day))


def _statistics_periods():
    """Only Django configures period choices; 1C accepts 1–90 inclusive days."""
    return list(
        StatisticsPeriodOption.objects.filter(enabled=True, days__gte=1, days__lte=90)
        .order_by("days")
        .values("days", "is_default")
    )


def _statistics_default(periods):
    return next(
        (item["days"] for item in periods if item["is_default"]),
        periods[0]["days"] if periods else None,
    )


def _check_statistics_manager(request):
    if request.active_role != UserRole.ADMIN:
        raise PermissionDenied("Статистика доступна только менеджеру.")


class OrderStatisticsPeriodsView(APIView):
    """Return Django Admin-configured options without contacting 1C."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        _check_statistics_manager(request)
        periods = _statistics_periods()
        return Response({
            "periods": [{"days": item["days"]} for item in periods],
            "defaultDays": _statistics_default(periods),
        })


class OrderStatisticsView(APIView):
    """Manager-only dashboard; calculations are authoritative in 1C."""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        _check_statistics_manager(request)

        periods = _statistics_periods()
        default_days = _statistics_default(periods)
        if default_days is None:
            raise ValidationError({"days": "В Django не настроены доступные периоды статистики."})

        days = request.query_params.get("days", str(default_days))
        allowed = {str(item["days"]) for item in periods}
        if days not in allowed or set(request.query_params) - {"days", "format"}:
            raise ValidationError({
                "days": "Выберите период из списка доступных в настройках Django.",
            })

        today = timezone.localdate()
        from_date = today - timedelta(days=int(days) - 1)
        data = OneCOrdersClient().statistics(*_actor(request), from_date, today)
        return Response(data)

class OrderViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        filters = _order_filters(request)
        records = OneCOrdersClient().list_orders(*_actor(request), filters=filters)
        return _list_response(records, request, self)

    def retrieve(self, request, pk=None):
        return Response(OneCOrdersClient().get(pk, *_actor(request)))

    def create(self, request):
        data = OneCOrdersClient().create(_order_payload(request), *_actor(request))
        return Response(data, status=status.HTTP_201_CREATED)

    def update(self, request, pk=None):
        return Response(OneCOrdersClient().patch(pk, _order_payload(request), *_actor(request)))

    def partial_update(self, request, pk=None):
        return Response(OneCOrdersClient().patch(pk, _order_payload(request), *_actor(request)))

    def destroy(self, request, pk=None):
        # 1C is the sole order owner; do not silently delete its documents.
        raise MethodNotAllowed("DELETE", detail="Удаление заказов через API не поддерживается.")

    @action(detail=True, methods=["get"], url_path="permissions")
    def permissions(self, request, pk=None):
        return Response(OneCOrdersClient().permissions(pk, *_actor(request)))

    @action(detail=True, methods=["post"], url_path="transition-status")
    def transition_status(self, request, pk=None):
        status_id = _uuid(request.data.get("statusId"), "statusId")
        reason = request.data.get("refusalReason", "")
        if not isinstance(reason, str):
            raise ValidationError({"refusalReason": "Причина отказа должна быть строкой."})
        return Response(OneCOrdersClient().transition_status(
            pk, status_id, *_actor(request), refusal_reason=reason
        ))

    @action(detail=True, methods=["post"], url_path="transition-work-status")
    def transition_work_status(self, request, pk=None):
        return Response(OneCOrdersClient().transition_work_status(
            pk, _uuid(request.data.get("statusId"), "statusId"), *_actor(request)
        ))

    @action(detail=True, methods=["post"], url_path="payment-status")
    def payment_status(self, request, pk=None):
        return Response(OneCOrdersClient().set_payment_status(
            pk, _uuid(request.data.get("statusId"), "statusId"), *_actor(request)
        ))

    @action(detail=False, methods=["get"], url_path="filter-permissions")
    def filter_permissions(self, request):
        allowed = {
            entry.filter_key for entry in OrderFilterPermission.objects.filter(
                role=request.active_role, enabled=True
            )
        }
        return Response({key: key in allowed for key, _ in OrderFilterKey.choices})
