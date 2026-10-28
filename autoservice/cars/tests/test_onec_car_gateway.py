"""Contract tests: 1C supplies IDs; never read vehicle Django tables."""
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

from cars.views import CarViewSet

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase
from PIL import Image
from rest_framework.exceptions import PermissionDenied, ValidationError

from cars.serializers import CarWriteSerializer
from integrations.services.onec_cars import OneCCarsClient, OneCCarError
from orders.views import _order_payload


OWNER = "8996ef81-9116-4d75-a3de-2fa8a5bc6b10"
CAR = "3bc5c300-d1e0-471e-8f4c-cc1f8610db8c"
BRAND = "21afe47c-5403-4805-9442-b1d10e84f97d"
MODEL = "8449407b-315d-4fa9-b058-2727c43a1b78"


@patch.dict("os.environ", {"ONEC_API_USER": "test-account", "ONEC_API_PASSWORD": "test-password"})
class OneCCarsContractTests(SimpleTestCase):
    @patch("cars.views.OneCUsersClient")
    @patch.object(CarViewSet, "_accessible")
    def test_owner_phone_filter_rejected_for_user_and_mechanic(self, accessible, users):
        accessible.return_value = []
        for role in ("user", "mechanic"):
            with self.subTest(role=role), self.assertRaises(PermissionDenied):
                request = SimpleNamespace(
                    active_role=role,
                    query_params={"owner_phone": "79998887766"},
                )
                CarViewSet()._queryset(request)
        users.assert_not_called()

    @patch("cars.views.OneCUsersClient")
    @patch.object(CarViewSet, "_accessible")
    def test_owner_phone_filter_allowed_for_manager(self, accessible, users):
        accessible.return_value = [
            {"id": CAR, "ownerId": OWNER, "status": "active", "brandName": "Toyota",
             "modelName": "Camry"}
        ]
        users.return_value.get_user.return_value = {"onecId": OWNER}
        request = SimpleNamespace(
            active_role="admin", query_params={"owner_phone": "79998887766"},
        )
        cars = CarViewSet()._queryset(request)
        self.assertEqual(len(cars), 1)
        users.return_value.get_user.assert_called_once()

    @patch("cars.views.get_native_profile")
    @patch("cars.views.OneCOrdersClient")
    def test_mechanic_car_details_do_not_include_owner_contact(self, gateway, lookup):
        car = {"id": CAR, "ownerId": OWNER, "photo": None}
        actor = SimpleNamespace(active_role="mechanic", user=SimpleNamespace(id=UUID(OWNER)))
        result = CarViewSet()._decorate(car, {"request": actor})
        self.assertEqual(result["ownerPhone"], "")
        self.assertEqual(result["ownerName"], "")
        lookup.assert_not_called()
        gateway.return_value.car_has_orders.assert_called_once()

    @patch("integrations.services.onec_cars.requests.request")
    @patch.dict("os.environ", {
        "ONEC_BASE_URL": "http://host.docker.internal:8081",
        "ONEC_API_USER": "",
        "ONEC_API_PASSWORD": "",
    })
    def test_internal_cars_work_without_service_credentials(self, request):
        request.return_value = SimpleNamespace(
            ok=True, json=lambda: [{"id": BRAND, "name": "Toyota"}]
        )
        records = OneCCarsClient().brands()
        self.assertEqual(records[0]["id"], BRAND)
        self.assertIsNone(request.call_args.kwargs["auth"])

    @patch.dict("os.environ", {
        "ONEC_BASE_URL": "https://external-1c.example.test",
        "ONEC_API_USER": "",
        "ONEC_API_PASSWORD": "",
    })
    def test_external_1c_requires_credentials(self):
        with self.assertRaises(OneCCarError) as error:
            OneCCarsClient()
        self.assertEqual(error.exception.status_code, 503)

    @patch.dict("os.environ", {
        "ONEC_BASE_URL": "http://host.docker.internal:8081",
        "ONEC_API_USER": "half-configured",
        "ONEC_API_PASSWORD": "",
    })
    def test_partial_credentials_are_rejected(self):
        with self.assertRaises(OneCCarError) as error:
            OneCCarsClient()
        self.assertEqual(error.exception.status_code, 503)

    @patch("integrations.services.onec_cars.requests.request")
    @patch.dict("os.environ", {
        "ONEC_BASE_URL": "https://external-1c.example.test",
        "ONEC_API_USER": "service",
        "ONEC_API_PASSWORD": "secret",
    })
    def test_external_1c_preserves_basic_auth(self, request):
        request.return_value = SimpleNamespace(
            ok=True, json=lambda: [{"id": BRAND, "name": "Toyota"}]
        )
        self.assertEqual(OneCCarsClient().brands()[0]["id"], BRAND)
        self.assertEqual(request.call_args.kwargs["auth"], ("service", "secret"))

    @patch("integrations.services.onec_cars.requests.request")
    @patch.dict("os.environ", {"ONEC_BASE_URL": "http://host.docker.internal:8081"})
    def test_brands_have_native_uuid(self, request):
        request.return_value = SimpleNamespace(
            ok=True, json=lambda: [{"id": BRAND, "name": "Toyota"}]
        )
        records = OneCCarsClient().brands()
        self.assertEqual(records[0]["id"], BRAND)
        self.assertIn("/ServiceCar/hs/api/car-brands", request.call_args.args[1])

    @patch("integrations.services.onec_cars.requests.request")
    @patch.dict("os.environ", {"ONEC_BASE_URL": "http://host.docker.internal:8081"})
    def test_cars_return_only_1c_identifiers(self, request):
        record = {
            "id": CAR, "ownerId": OWNER, "brand": BRAND, "model": MODEL,
            "brandName": "Toyota", "modelName": "Camry",
            "year": 2020, "status": "active", "vin": "", "plate_number": "",
        }
        request.return_value = SimpleNamespace(ok=True, json=lambda: record)
        self.assertEqual(OneCCarsClient().get(CAR)["ownerId"], OWNER)

    def test_invalid_uuid_rejected_before_1c_call(self):
        with self.assertRaises(OneCCarError):
            OneCCarsClient().get("not-uuid")

    def test_vin_rejects_forbidden_symbols(self):
        serializer = CarWriteSerializer(data={
            "brand": BRAND, "model": MODEL, "year": 2020, "vin": "IOQ00000000000000"
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn("vin", serializer.errors)

    def test_order_payload_uses_native_car_uuid_without_local_order_models(self):
        request = SimpleNamespace(data={
            "car": CAR, "works": [], "description": "Осмотр",
        })
        payload = _order_payload(request)
        self.assertEqual(payload["car"], CAR)
        self.assertEqual(payload["works"], [])

    def test_order_payload_rejects_custom_work_name(self):
        request = SimpleNamespace(data={
            "car": CAR, "works": [{"name": "Произвольная работа"}],
        })
        with self.assertRaises(ValidationError):
            _order_payload(request)

    @patch("orders.views.validate_filter_permissions")
    @patch("cars.views.OneCOrdersClient")
    @patch.object(CarViewSet, "_get_authorized")
    def test_car_order_list_page_one_does_not_raise_name_error(
        self, get_car, gateway, validate_filters,
    ):
        get_car.return_value = {"id": CAR}
        gateway.return_value.car_orders.return_value = []
        api_request = SimpleNamespace(
            user=SimpleNamespace(id=UUID(OWNER), pk=UUID(OWNER)),
            active_role="user",
            query_params={"page": "1"},
        )

        response = CarViewSet().orders(api_request, pk=CAR)

        self.assertEqual(response.data["count"], 0)
        self.assertEqual(response.data["results"], [])
        validate_filters.assert_called_once_with(api_request)
        gateway.return_value.car_orders.assert_called_once_with(
            CAR, UUID(OWNER), "user", filters={},
        )

    @patch.object(CarViewSet, "_validate_brand_model")
    @patch.object(CarViewSet, "_decorate")
    @patch.object(CarViewSet, "_get_authorized")
    @patch("cars.views.OneCCarsClient")
    @patch("cars.views.OneCOrdersClient")
    def test_patch_plate_number_without_photo(
        self, orders_gateway, cars_gateway, get_car, decorate, validate_brand_model,
    ):
        car = {
            "id": CAR, "status": "active", "ownerId": OWNER,
            "brand": BRAND, "model": MODEL, "year": 2025,
            "vin": "", "plate_number": "",
        }
        get_car.return_value = car
        orders_gateway.return_value.car_has_orders.return_value = True
        cars_gateway.return_value.patch.return_value = {
            **car, "plate_number": "A550B4",
        }
        decorate.side_effect = lambda item, context: item
        request = SimpleNamespace(
            user=SimpleNamespace(id=UUID(OWNER), pk=UUID(OWNER)),
            active_role="user",
            data={"plate_number": "A550B4"},
        )

        response = CarViewSet().partial_update(request, pk=CAR)

        self.assertEqual(response.data["plate_number"], "A550B4")
        cars_gateway.return_value.patch.assert_called_once_with(
            CAR, {"plate_number": "A550B4"},
        )


    @patch.object(CarViewSet, "_validate_brand_model")
    @patch.object(CarViewSet, "_decorate")
    @patch.object(CarViewSet, "_get_authorized")
    @patch("cars.views.OneCCarsClient")
    @patch("cars.views.OneCOrdersClient")
    def test_patch_image_is_transformed_to_base64_for_1c(
        self, orders_gateway, cars_gateway, get_car, decorate, validate_brand_model,
    ):
        car = {
            "id": CAR, "status": "active", "ownerId": OWNER,
            "brand": BRAND, "model": MODEL, "year": 2025,
            "vin": "", "plate_number": "",
        }
        get_car.return_value = car
        orders_gateway.return_value.car_has_orders.return_value = True
        cars_gateway.return_value.patch.return_value = car
        decorate.side_effect = lambda item, context: item
        buffer = BytesIO()
        Image.new("RGB", (2, 2)).save(buffer, format="PNG")
        picture = SimpleUploadedFile(
            "car.png", buffer.getvalue(), content_type="image/png",
        )
        request = SimpleNamespace(
            user=SimpleNamespace(id=UUID(OWNER), pk=UUID(OWNER)),
            active_role="user",
            data={"photo": picture, "plate_number": "A550B4"},
        )

        CarViewSet().partial_update(request, pk=CAR)

        kwargs = cars_gateway.return_value.patch.call_args
        self.assertEqual(kwargs.args[0], CAR)
        self.assertEqual(kwargs.args[1]["plate_number"], "A550B4")
        self.assertEqual(kwargs.args[1]["photoMime"], "image/png")
        import base64
        self.assertEqual(
            base64.b64decode(kwargs.args[1]["photoBase64"]),
            buffer.getvalue(),
        )
        self.assertNotIn("photo", kwargs.args[1])


    def test_photo_exactly_five_megabytes_is_accepted(self):
        picture = SimpleUploadedFile(
            "car.jpg", b"x" * 5_000_000, content_type="image/jpeg",
        )
        fields = {"photo": picture}
        CarViewSet._prepare_photo(fields)

        import base64
        self.assertEqual(len(base64.b64decode(fields["photoBase64"])), 5_000_000)
        self.assertEqual(fields["photoMime"], "image/jpeg")
        self.assertNotIn("photo", fields)

    def test_photo_over_five_megabytes_is_rejected(self):
        picture = SimpleUploadedFile(
            "car.jpg", b"x" * 5_000_001, content_type="image/jpeg",
        )
        with self.assertRaises(ValidationError) as error:
            CarViewSet._prepare_photo({"photo": picture})
        self.assertIn("5 МБ", str(error.exception))
