"""Offline contract tests for the *inactive* 1C orders gateway (no DB/1C needed)."""
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from integrations.services.onec_orders import OneCOrderError, OneCOrdersClient


ACTOR = "8996ef81-9116-4d75-a3de-2fa8a5bc6b10"
CAR = "3bc5c300-d1e0-471e-8f4c-cc1f8610db8c"
ORDER = "21afe47c-5403-4805-9442-b1d10e84f97d"
OTHER_ORDER = "8449407b-315d-4fa9-b058-2727c43a1b78"
STATUS = "575274d0-f291-4826-8dc5-97cfa32d9ab1"


def api_response(data, status=200):
    return SimpleNamespace(
        ok=200 <= status < 300,
        status_code=status,
        json=lambda: data,
    )


def order_record(identifier=ORDER):
    return {
        "id": identifier,
        "car": CAR,
        "orderNumber": "000000001",
        "status": {"id": STATUS, "code": "under_review", "name": "На рассмотрении"},
    }


@patch.dict("os.environ", {
    "ONEC_BASE_URL": "http://host.docker.internal:8081",
    "ONEC_API_USER": "",
    "ONEC_API_PASSWORD": "",
})
class OneCOrdersGatewayTests(SimpleTestCase):
    @patch("integrations.services.onec_orders.requests.request")
    def test_internal_api_uses_no_basic_credentials(self, request):
        request.return_value = api_response([order_record()])
        result = OneCOrdersClient().list_orders(ACTOR, "user")
        self.assertEqual(result[0]["id"], ORDER)
        self.assertIsNone(request.call_args.kwargs["auth"])
        self.assertIn("/ServiceCar/hs/api/orders", request.call_args.args[1])
        self.assertEqual(request.call_args.kwargs["params"]["actorId"], ACTOR)
        self.assertEqual(request.call_args.kwargs["params"]["actorRole"], "user")

    @patch("integrations.services.onec_orders.requests.request")
    def test_create_sends_body_and_actor_separately(self, request):
        request.return_value = api_response(order_record(), 201)
        payload = {"car": CAR, "description": "Диагностика"}
        result = OneCOrdersClient().create(payload, ACTOR, "user")
        self.assertEqual(result["car"], CAR)
        self.assertEqual(request.call_args.kwargs["json"], payload)
        self.assertEqual(request.call_args.kwargs["params"]["actorId"], ACTOR)

    @patch("integrations.services.onec_orders.requests.request")
    def test_create_allows_no_works(self, request):
        request.return_value = api_response(order_record(), 201)
        client = OneCOrdersClient()
        self.assertEqual(
            client.create({"car": CAR, "works": []}, ACTOR, "user")["id"],
            ORDER,
        )
        self.assertEqual(request.call_args.kwargs["json"]["works"], [])
        self.assertEqual(
            client.patch(ORDER, {"description": "Без работ"}, ACTOR, "user")["id"],
            ORDER,
        )

    @patch("integrations.services.onec_orders.requests.request")
    def test_create_uses_catalog_work_id(self, request):
        request.return_value = api_response(order_record(), 201)
        OneCOrdersClient().create(
            {"car": CAR, "works": [{"workTypeId": STATUS}]},
            ACTOR, "user",
        )
        self.assertEqual(
            request.call_args.kwargs["json"]["works"][0]["workTypeId"], STATUS
        )

    @patch("integrations.services.onec_orders.requests.request")
    def test_free_text_works_are_rejected_before_http(self, request):
        client = OneCOrdersClient()
        bad_payloads = (
            {"workTypes": ["Моя работа"]},
            {"works": [{"name": "Моя работа", "price": "1.00"}]},
            {"works": [{"workTypeId": None}]},
            {"works": [{"workTypeId": STATUS, "name": "Подмена"}]},
            {"works": [{"workTypeId": STATUS}, {"workTypeId": STATUS}]},
        )
        for payload in bad_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(OneCOrderError) as error:
                    client.create(payload, ACTOR, "user")
                self.assertEqual(error.exception.status_code, 400)
        request.assert_not_called()

    def test_status_change_has_no_hardcoded_transition_graph(self):
        # Order gateway forwards manager's target UUID; 1C validates role,
        # target catalog entry and current order independently.
        request_payload = {"statusId": STATUS, "refusalReason": ""}
        with patch("integrations.services.onec_orders.requests.request") as request:
            request.return_value = api_response(order_record())
            OneCOrdersClient().transition_status(ORDER, STATUS, ACTOR, "admin")
            self.assertEqual(request.call_args.kwargs["json"], request_payload)

    def test_bad_role_is_rejected(self):
        with self.assertRaises(OneCOrderError) as error:
            OneCOrdersClient().list_orders(ACTOR, "superuser")
        self.assertEqual(error.exception.status_code, 403)

    def test_bad_uuid_is_rejected(self):
        with self.assertRaises(OneCOrderError) as error:
            OneCOrdersClient().get("123-not-uuid", ACTOR, "user")
        self.assertEqual(error.exception.status_code, 400)

    def test_invalid_filter_cannot_override_actor(self):
        with self.assertRaises(OneCOrderError):
            OneCOrdersClient().list_orders(ACTOR, "user", {"actorRole": "admin"})

    @patch("integrations.services.onec_orders.requests.request")
    def test_mismatched_order_uuid_is_rejected(self, request):
        request.return_value = api_response(order_record(OTHER_ORDER))
        with self.assertRaises(OneCOrderError) as error:
            OneCOrdersClient().get(ORDER, ACTOR, "user")
        self.assertIn("другой заказ", str(error.exception.detail))

    @patch("integrations.services.onec_orders.requests.request")
    def test_business_validation_error_preserves_status(self, request):
        request.return_value = api_response(
            {"code": "invalid_transition", "message": "Переход недоступен."},
            409,
        )
        with self.assertRaises(OneCOrderError) as error:
            OneCOrdersClient().transition_work_status(
                ORDER, STATUS, ACTOR, "admin"
            )
        self.assertEqual(error.exception.status_code, 409)

    @patch("integrations.services.onec_orders.requests.request")
    def test_internal_1c_create_error_exposes_only_safe_event_id(self, request):
        event_id = "e1554ed0-2508-4dd0-b5c1-8b9e99e83c6f"
        request.return_value = api_response({
            "code": "order_create_failed",
            "message": "Ошибка сохранения заказа в 1С. Код события: " + event_id,
        }, 500)
        with self.assertRaises(OneCOrderError) as error:
            OneCOrdersClient().create({"car": CAR, "works": []}, ACTOR, "user")
        self.assertEqual(error.exception.status_code, 502)
        self.assertEqual(str(error.exception.detail),
                         "Ошибка сохранения заказа в 1С. Код события: " + event_id)

    @patch("integrations.services.onec_orders.requests.request")
    def test_500_does_not_expose_arbitrary_1c_diagnostics(self, request):
        request.return_value = api_response({
            "code": "order_create_failed",
            "message": "Секретный стек 1С и SQL не должен попадать клиенту",
        }, 500)
        with self.assertRaises(OneCOrderError) as error:
            OneCOrdersClient().create({"car": CAR, "works": []}, ACTOR, "user")
        self.assertEqual(error.exception.status_code, 502)
        self.assertNotIn("Секретный", str(error.exception.detail))

    @patch("integrations.services.onec_orders.requests.request")
    def test_rejects_invalid_json(self, request):
        response = api_response({})
        response.json = lambda: (_ for _ in ()).throw(ValueError("invalid"))
        request.return_value = response
        with self.assertRaises(OneCOrderError) as error:
            OneCOrdersClient().schedule(ACTOR, "admin")
        self.assertEqual(error.exception.status_code, 502)

    @patch("integrations.services.onec_orders.requests.request")
    def test_availability_checks_date_format(self, request):
        with self.assertRaises(OneCOrderError):
            OneCOrdersClient().availability(ACTOR, "user", "wrong-date")
        request.assert_not_called()

    @patch.dict("os.environ", {
        "ONEC_BASE_URL": "https://external.example.test",
        "ONEC_API_USER": "",
        "ONEC_API_PASSWORD": "",
    })
    def test_external_api_requires_both_credentials(self):
        with self.assertRaises(OneCOrderError) as error:
            OneCOrdersClient()
        self.assertEqual(error.exception.status_code, 503)

    @patch.dict("os.environ", {
        "ONEC_BASE_URL": "http://host.docker.internal:8081",
        "ONEC_API_USER": "user",
        "ONEC_API_PASSWORD": "",
    })
    def test_partially_configured_credentials_fail(self):
        with self.assertRaises(OneCOrderError) as error:
            OneCOrdersClient()
        self.assertEqual(error.exception.status_code, 503)

    @patch("integrations.services.onec_orders.requests.request")
    @patch.dict("os.environ", {
        "ONEC_BASE_URL": "https://external.example.test",
        "ONEC_API_USER": "integration",
        "ONEC_API_PASSWORD": "secret",
    })
    def test_external_api_uses_basic_auth(self, request):
        request.return_value = api_response([])
        self.assertEqual(OneCOrdersClient().order_statuses(ACTOR, "admin"), [])
        self.assertEqual(
            request.call_args.kwargs["auth"], ("integration", "secret")
        )


    @patch("integrations.services.onec_orders.requests.request")
    def test_statistics_proxies_manager_context_and_dates(self, request):
        payload = {
            "period": {"from": "2026-10-01", "to": "2026-10-22", "days": 22},
            "summary": {"orders": 0, "completed": 0, "workAmount": 0, "occupancyPercent": 0},
            "ordersTrend": [], "statusDistribution": [],
            "topWorkTypes": [], "weekdayOccupancy": [],
        }
        request.return_value = api_response(payload)
        result = OneCOrdersClient().statistics(
            ACTOR, "admin", date(2026, 10, 1), date(2026, 10, 22)
        )
        self.assertEqual(result["summary"]["orders"], 0)
        self.assertIn("/statistics/orders", request.call_args.args[1])
        self.assertEqual(request.call_args.kwargs["params"]["from"], "2026-10-01")
        self.assertEqual(request.call_args.kwargs["params"]["to"], "2026-10-22")
        self.assertEqual(request.call_args.kwargs["params"]["actorRole"], "admin")
        self.assertEqual(request.call_args.kwargs["timeout"], 30)

    @patch("integrations.services.onec_orders.requests.request")
    def test_statistics_rejects_incomplete_response(self, request):
        request.return_value = api_response({"summary": {"orders": 0}})
        with self.assertRaises(OneCOrderError):
            OneCOrdersClient().statistics(
                ACTOR, "admin", date(2026, 10, 1), date(2026, 10, 22)
            )

