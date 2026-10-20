"""Vehicle HTTP API facade: 1C owns cars, Django owns auth and order links."""
from uuid import UUID

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from cars.pagination import CarPagination
from cars.serializers import CarWriteSerializer, CarSerializer
from integrations.services.onec_cars import OneCCarsClient, OneCCarError, canonical_uuid
from integrations.services.onec_users import OneCUsersClient
from orders.filters import OrderFilter
from orders.models import Order
from orders.pagination import OrderPagination
from orders.permissions import validate_filter_permissions
from orders.serializers import OrderSerializer
from users.auth.services import PhoneNormalizer
from users.models import UserRole
from users.onec_lookup import get_native_profile, native_display_name


def _same_uuid(a, b):
    return str(a).lower() == str(b).lower()


class CarBrandViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        return Response(OneCCarsClient().brands())

    def retrieve(self, request, pk=None):
        identifier = canonical_uuid(pk)
        brand = next(
            (x for x in OneCCarsClient().brands() if _same_uuid(x["id"], identifier)),
            None,
        )
        if brand is None:
            raise NotFound("Марка не найдена.")
        return Response(brand)


class CarModelViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request):
        brand = request.query_params.get("brand")
        return Response(OneCCarsClient().models(brand=brand))

    def retrieve(self, request, pk=None):
        identifier = canonical_uuid(pk)
        model = next(
            (x for x in OneCCarsClient().models() if _same_uuid(x["id"], identifier)),
            None,
        )
        if model is None:
            raise NotFound("Модель не найдена.")
        return Response(model)


class CarViewSet(viewsets.ViewSet):
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = CarPagination

    def _accessible(self, request):
        client = OneCCarsClient()
        if request.active_role == UserRole.USER:
            records = client.list_cars(owner=request.user.id)
            # Do not trust the filtering done by the remote service alone.
            return [x for x in records if _same_uuid(x["ownerId"], request.user.id)]
        records = client.list_cars()
        if request.active_role == UserRole.MECHANIC:
            allowed = {
                str(x).lower()
                for x in Order.objects.filter(
                    mechanic_links__mechanic_id=request.user.id
                ).values_list("car_id", flat=True)
            }
            return [x for x in records if x["id"].lower() in allowed]
        if request.active_role == UserRole.ADMIN:
            return records
        raise PermissionDenied("Недопустимая роль.")

    def _queryset(self, request):
        records = self._accessible(request)
        role = request.active_role
        state = request.query_params.get("status")
        if state not in ("active", "archived", "all"):
            state = "all" if role == UserRole.ADMIN else "active"
        if state != "all":
            records = [x for x in records if x["status"] == state]

        if role in (UserRole.MECHANIC, UserRole.ADMIN):
            owner_phone = request.query_params.get("owner_phone")
            if owner_phone:
                profile = OneCUsersClient().get_user(
                    PhoneNormalizer.normalize(owner_phone)
                )
                records = [x for x in records
                           if _same_uuid(x["ownerId"], profile["onecId"])]

        for field in ("brand", "model"):
            identifier = request.query_params.get(field)
            if identifier:
                identifier = canonical_uuid(identifier)
                records = [x for x in records if _same_uuid(x[field], identifier)]

        year = request.query_params.get("year")
        if year:
            try:
                records = [x for x in records if x["year"] == int(year)]
            except ValueError:
                pass
        for field in ("vin", "plate_number"):
            needle = request.query_params.get(field)
            if needle:
                records = [x for x in records if needle.strip().casefold()
                           in (x.get(field) or "").casefold()]
        return sorted(records, key=lambda x: (
            x["brandName"].casefold(), x["modelName"].casefold(), x["id"]
        ))

    def _get_authorized(self, request, pk):
        identifier = canonical_uuid(pk)
        car = OneCCarsClient().get(identifier)
        if request.active_role == UserRole.USER:
            if not _same_uuid(car["ownerId"], request.user.id):
                raise NotFound("Автомобиль не найден.")
        elif request.active_role == UserRole.MECHANIC:
            if not Order.objects.filter(
                car_id=identifier,
                mechanic_links__mechanic_id=request.user.id,
            ).exists():
                raise NotFound("Автомобиль не найден.")
        elif request.active_role != UserRole.ADMIN:
            raise PermissionDenied("Недопустимая роль.")
        return car

    def _decorate(self, car, context):
        result = dict(car)
        owner = get_native_profile(car["ownerId"], context)
        result["ownerName"] = native_display_name(owner)
        result["ownerPhone"] = owner["phone"]
        result["hasOrders"] = Order.objects.filter(car_id=car["id"]).exists()
        # Photos require a separate migration to native 1C storage.
        result["photo"] = None
        return result

    def list(self, request):
        records = self._queryset(request)
        paginator = CarPagination()
        page = paginator.paginate_queryset(records, request, view=self)
        context = {"request": request}
        return paginator.get_paginated_response(
            CarSerializer([self._decorate(x, context) for x in page], many=True).data
        )

    def retrieve(self, request, pk=None):
        car = self._get_authorized(request, pk)
        return Response(CarSerializer(self._decorate(car, {"request": request})).data)

    @action(detail=True, methods=["get"])
    def navigation(self, request, pk=None):
        car = self._get_authorized(request, pk)
        records = self._queryset(request)
        current_index = next(
            (i for i, item in enumerate(records) if _same_uuid(item["id"], car["id"])),
            None,
        )
        if current_index is None:
            raise NotFound("Автомобиль не найден в текущем списке.")
        context = {"request": request}
        previous = (self._decorate(records[current_index - 1], context)
                    if current_index else None)
        following = (self._decorate(records[current_index + 1], context)
                     if current_index + 1 < len(records) else None)
        return Response({
            "previous": CarSerializer(previous).data if previous else None,
            "next": CarSerializer(following).data if following else None,
        })

    @action(detail=True, methods=["get"])
    def orders(self, request, pk=None):
        car = self._get_authorized(request, pk)
        validate_filter_permissions(request)
        orders = Order.objects.filter(
            car_id=car["id"], customer_id=request.user.id,
        ).select_related(
            "status", "work_status", "payment_status", "busy_slot"
        ).prefetch_related("works__work_type").order_by("-created_at")
        orders = OrderFilter(request.query_params, queryset=orders, request=request).qs
        paginator = OrderPagination()
        page = paginator.paginate_queryset(orders, request, view=self)
        return paginator.get_paginated_response(
            OrderSerializer(page, many=True, context={"request": request}).data
        )

    @staticmethod
    def _no_photo(request):
        # Never silently discard user-supplied photos during transition.
        if "photo" in request.data and request.data.get("photo") not in (None, ""):
            raise ValidationError({"photo": "Загрузка фото в 1С пока не подключена."})

    @staticmethod
    def _validate_brand_model(data):
        # Server-side cross-catalog validation, repeated inside 1C itself.
        client = OneCCarsClient()
        if "brand" in data and "model" in data:
            if not any(_same_uuid(x["id"], data["model"])
                       for x in client.models(brand=data["brand"])):
                raise ValidationError({
                    "model": "Выбранная модель не относится к указанной марке."
                })

    def create(self, request):
        if request.active_role != UserRole.USER:
            raise PermissionDenied("Только пользователь может добавлять автомобили.")
        self._no_photo(request)
        serializer = CarWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fields = dict(serializer.validated_data)
        self._validate_brand_model(fields)
        fields["ownerId"] = str(request.user.id)
        for field in ("brand", "model"):
            fields[field] = str(fields[field])
        result = OneCCarsClient().create(fields)
        if not _same_uuid(result["ownerId"], request.user.id):
            raise OneCCarError("identity_mismatch", "1С вернула неверного владельца.")
        return Response(CarSerializer(self._decorate(result, {"request": request})).data,
                        status=status.HTTP_201_CREATED)

    def _update(self, request, pk, partial):
        if request.active_role != UserRole.USER:
            raise PermissionDenied("Только владелец может изменять автомобиль.")
        car = self._get_authorized(request, pk)
        if car["status"] == "archived":
            raise ValidationError({"detail": "Архивный автомобиль нельзя изменять."})
        self._no_photo(request)
        serializer = CarWriteSerializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        fields = dict(serializer.validated_data)
        if Order.objects.filter(car_id=car["id"]).exists():
            immutable = ("brand", "model", "year", "vin")
            changed = [
                name for name in immutable
                if name in fields
                and str(fields[name] or "").upper() != str(car[name] or "").upper()
            ]
            if changed:
                raise ValidationError({name: "Поле нельзя изменить при наличии заказов."
                                       for name in changed})
        checked = dict(car)
        checked.update(fields)
        self._validate_brand_model(checked)
        for field in ("brand", "model"):
            if field in fields:
                fields[field] = str(fields[field])
        result = OneCCarsClient().patch(car["id"], fields)
        if not _same_uuid(result["ownerId"], request.user.id):
            raise OneCCarError("identity_mismatch", "1С вернула неверного владельца.")
        return Response(CarSerializer(self._decorate(result, {"request": request})).data)

    def update(self, request, pk=None):
        return self._update(request, pk, partial=False)

    def partial_update(self, request, pk=None):
        return self._update(request, pk, partial=True)

    def destroy(self, request, pk=None):
        if request.active_role != UserRole.USER:
            raise PermissionDenied("Только владелец может архивировать автомобиль.")
        car = self._get_authorized(request, pk)
        OneCCarsClient().archive(car["id"])
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["post"])
    def restore(self, request, pk=None):
        if request.active_role != UserRole.USER:
            raise PermissionDenied("Только пользователь может восстанавливать автомобиль.")
        car = self._get_authorized(request, pk)
        if car["status"] != "archived":
            raise ValidationError({"detail": "Автомобиль уже активен."})
        result = OneCCarsClient().restore(car["id"])
        return Response(CarSerializer(self._decorate(result, {"request": request})).data)
