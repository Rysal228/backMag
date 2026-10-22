import base64
"""Vehicle HTTP API facade: 1C owns cars, Django owns auth and order links."""
from uuid import UUID

from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from cars.pagination import CarPagination
from cars.serializers import CarWriteSerializer, CarSerializer
from integrations.services.onec_cars import OneCCarsClient, OneCCarError, canonical_uuid
from integrations.services.onec_users import OneCUsersClient
from integrations.services.onec_orders import OneCOrdersClient
from orders.views import _actor, _list_response, _order_filters
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
            records_for_role = OneCOrdersClient().list_orders(*_actor(request))
            allowed = {
                item["car"].lower() for item in records_for_role
                if str(request.user.id).lower() in {
                    str(uid).lower() for uid in item.get("mechanics", [])
                }
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
            if not any(
                str(request.user.id).lower() in {
                    str(uid).lower() for uid in item.get("mechanics", [])
                } for item in OneCOrdersClient().car_orders(
                    identifier, *_actor(request)
                )
            ):
                raise NotFound("Автомобиль не найден.")
        elif request.active_role != UserRole.ADMIN:
            raise PermissionDenied("Недопустимая роль.")
        return car

    def _decorate(self, car, context):
        result = dict(car)
        owner = get_native_profile(car["ownerId"], context)
        result["ownerName"] = native_display_name(owner)
        result["ownerPhone"] = owner["phone"]
        request = context["request"]
        result["hasOrders"] = OneCOrdersClient().car_has_orders(
            car["id"], *_actor(request)
        )
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
        # _order_filters already enforces Django filter permissions.
        orders = OneCOrdersClient().car_orders(
            car["id"], *_actor(request), filters=_order_filters(request)
        )
        return _list_response(orders, request, self)

    @staticmethod
    def _prepare_photo(fields):
        file = fields.pop("photo", ...)
        if file is ...:
            return
        if file is None:
            raise ValidationError({"photo": "Очистка фотографии пока не поддерживается."})
        if file.size > 5_000_000:
            raise ValidationError({"photo": "Фотография не должна превышать 5 МБ."})
        mime = getattr(file, "content_type", None)
        if mime not in ("image/jpeg", "image/png", "image/webp"):
            raise ValidationError({"photo": "Допустимые форматы: JPEG, PNG и WebP."})
        fields["photoBase64"] = base64.b64encode(file.read()).decode("ascii")
        fields["photoMime"] = mime

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
        serializer = CarWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fields = dict(serializer.validated_data)
        self._prepare_photo(fields)
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
        serializer = CarWriteSerializer(data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        fields = dict(serializer.validated_data)
        self._prepare_photo(fields)
        if OneCOrdersClient().car_has_orders(car["id"], *_actor(request)):
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
