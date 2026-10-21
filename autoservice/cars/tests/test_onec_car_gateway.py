"""Contract tests: 1C supplies IDs; never read vehicle Django tables."""
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError

from cars.serializers import CarWriteSerializer
from integrations.services.onec_cars import OneCCarsClient, OneCCarError
from orders.views import _order_payload


OWNER = "8996ef81-9116-4d75-a3de-2fa8a5bc6b10"
CAR = "3bc5c300-d1e0-471e-8f4c-cc1f8610db8c"
BRAND = "21afe47c-5403-4805-9442-b1d10e84f97d"
MODEL = "8449407b-315d-4fa9-b058-2727c43a1b78"


@patch.dict("os.environ", {"ONEC_API_USER": "test-account", "ONEC_API_PASSWORD": "test-password"})
class OneCCarsContractTests(SimpleTestCase):
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
