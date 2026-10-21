"""Preparatory 1C order gateway. Not used by existing Django order routes yet.

Only 1C will own the order workflow after cutover. The 1C endpoint MUST verify
actor identity/role against its own application-user catalog/roles register.
Keep its HTTP publication on the trusted backend-only network.
"""
import os
from datetime import date
from urllib.parse import quote
from uuid import UUID

import requests
from rest_framework.exceptions import APIException

from integrations.services.onec_users import DEFAULT_BASE_URL


class OneCOrderError(APIException):
    status_code = 502
    default_detail = "Ошибка сервиса заказов 1С."
    default_code = "onec_order_error"

    def __init__(self, code, message, status_code=502):
        self.status_code = status_code
        super().__init__(detail=message, code=code)


def _uuid(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise OneCOrderError("invalid_id", "Некорректный идентификатор 1С.", 400) from exc


class OneCOrdersClient:
    """Private server-to-server JSON API; does not access Django Order ORM."""

    VALID_ROLES = frozenset(("user", "mechanic", "admin"))
    LIST_FILTERS = frozenset((
        "search", "order_number", "vin", "plate_number",
        "brand", "model", "work_type", "status", "work_status",
        "date_from", "date_to", "car",
    ))

    def __init__(self):
        self.base = os.environ.get("ONEC_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        self.path = os.environ.get("ONEC_ORDERS_PATH", "/ServiceCar/hs/api").strip("/")
        self.user = os.environ.get("ONEC_API_USER")
        self.password = os.environ.get("ONEC_API_PASSWORD")
        self.allow_internal = self.base == DEFAULT_BASE_URL
        # Same internal-only compatibility behavior as OneCUsersClient.
        if bool(self.user) != bool(self.password):
            raise OneCOrderError(
                "onec_credentials_invalid", "Учётные данные 1С настроены неполностью.", 503
            )
        if not self.user and not self.allow_internal:
            raise OneCOrderError(
                "onec_credentials_missing", "Не настроен защищённый доступ Django к 1С.", 503
            )

    @classmethod
    def _actor(cls, actor_id, actor_role):
        if actor_role not in cls.VALID_ROLES:
            raise OneCOrderError("invalid_role", "Недопустимая активная роль.", 403)
        return {"actorId": _uuid(actor_id), "actorRole": actor_role}

    @staticmethod
    def _order_id(value):
        return quote(_uuid(value), safe="")

    def _request(self, method, resource, *, actor_id, actor_role, params=None, payload=None):
        if not resource or any(s in resource for s in ("?", "#", "..", "//")):
            raise ValueError("Invalid 1C API resource path")

        url = f"{self.base}/{self.path}/{resource.lstrip('/')}"
        context = self._actor(actor_id, actor_role)
        query = dict(params or {})
        if "actorId" in query or "actorRole" in query:
            raise ValueError("Caller must not override actor context")
        query.update(context)

        try:
            response = requests.request(
                method,
                url,
                params=query,
                json=payload,
                auth=(self.user, self.password) if self.user else None,
                headers={"Accept": "application/json"},
                timeout=10,
                allow_redirects=False,
            )
        except requests.Timeout as exc:
            raise OneCOrderError("onec_timeout", "1С не ответила вовремя.", 504) from exc
        except requests.RequestException as exc:
            raise OneCOrderError("onec_unavailable", "Нет соединения с 1С.") from exc

        if response.status_code == 204:
            return None
        try:
            body = response.json()
        except ValueError as exc:
            raise OneCOrderError(
                "invalid_response", "1С вернула некорректный JSON."
            ) from exc

        if not response.ok:
            if (
                response.status_code in (400, 403, 404, 409)
                and isinstance(body, dict)
                and isinstance(body.get("code"), str)
                and isinstance(body.get("message"), str)
            ):
                raise OneCOrderError(
                    body["code"], body["message"], response.status_code
                )
            raise OneCOrderError(
                "onec_http_error", "Сервис заказов 1С вернул ошибку."
            )
        return body

    @staticmethod
    def _array(value):
        if not isinstance(value, list):
            raise OneCOrderError(
                "invalid_response", "1С вернула некорректный список."
            )
        return value

    @staticmethod
    def _mapping(value):
        if not isinstance(value, dict):
            raise OneCOrderError(
                "invalid_response", "1С вернула некорректный объект."
            )
        return value

    @classmethod
    def _order(cls, value):
        value = cls._mapping(value)
        _uuid(value.get("id"))
        _uuid(value.get("car"))
        status = value.get("status")
        if not isinstance(status, dict) or not isinstance(status.get("code"), str):
            raise OneCOrderError(
                "invalid_response", "1С вернула заказ без статуса."
            )
        return value

    def work_types(self, actor_id, actor_role, search=""):
        params = {"search": search} if search else None
        return self._array(self._request(
            "GET", "order-work-types", actor_id=actor_id, actor_role=actor_role,
            params=params,
        ))

    def order_statuses(self, actor_id, actor_role):
        return self._array(self._request(
            "GET", "order-statuses", actor_id=actor_id, actor_role=actor_role,
        ))

    def work_statuses(self, actor_id, actor_role):
        return self._array(self._request(
            "GET", "order-work-statuses", actor_id=actor_id, actor_role=actor_role,
        ))

    def payment_statuses(self, actor_id, actor_role):
        return self._array(self._request(
            "GET", "order-payment-statuses", actor_id=actor_id, actor_role=actor_role,
        ))

    def schedule(self, actor_id, actor_role):
        return self._mapping(self._request(
            "GET", "order-schedule", actor_id=actor_id, actor_role=actor_role,
        ))

    def availability(self, actor_id, actor_role, target_date):
        try:
            normalized = date.fromisoformat(str(target_date)).isoformat()
        except (ValueError, TypeError) as exc:
            raise OneCOrderError("invalid_date", "Некорректная дата записи.", 400) from exc
        return self._mapping(self._request(
            "GET", "order-availability", actor_id=actor_id, actor_role=actor_role,
            params={"date": normalized},
        ))

    def list_orders(self, actor_id, actor_role, filters=None):
        filters = filters or {}
        unknown = set(filters) - self.LIST_FILTERS
        if unknown:
            raise OneCOrderError(
                "invalid_filter", "Неизвестный фильтр заказов.", 400
            )
        records = self._array(self._request(
            "GET", "orders", actor_id=actor_id, actor_role=actor_role,
            params=filters,
        ))
        return [self._order(item) for item in records]

    def get(self, order_id, actor_id, actor_role):
        record = self._order(self._request(
            "GET", f"orders/{self._order_id(order_id)}",
            actor_id=actor_id, actor_role=actor_role,
        ))
        if _uuid(record["id"]) != _uuid(order_id):
            raise OneCOrderError(
                "identity_mismatch", "1С вернула другой заказ."
            )
        return record

    @staticmethod
    def _check_works(payload):
        """An order may have no works; a work row must reference the 1C catalog."""
        if not isinstance(payload, dict):
            raise OneCOrderError("invalid_payload", "Тело заказа должно быть объектом.", 400)
        if "workTypes" in payload:
            raise OneCOrderError(
                "catalog_works_only",
                "Передавайте идентификаторы работ из справочника, а не названия.",
                400,
            )
        if "works" not in payload:
            return
        works = payload["works"]
        if not isinstance(works, list):
            raise OneCOrderError("invalid_works", "Работы должны быть массивом.", 400)
        seen = set()
        for work in works:
            if not isinstance(work, dict):
                raise OneCOrderError(
                    "invalid_works", "Каждая работа должна быть объектом.", 400
                )
            if set(work) - {"id", "workTypeId", "price"}:
                raise OneCOrderError(
                    "catalog_works_only",
                    "Произвольные названия работ не поддерживаются.",
                    400,
                )
            if not work.get("workTypeId"):
                raise OneCOrderError(
                    "work_type_required",
                    "Для каждой строки выберите вид работы из справочника.",
                    400,
                )
            kind = _uuid(work["workTypeId"])
            if kind in seen:
                raise OneCOrderError(
                    "duplicate_work_type",
                    "Нельзя выбрать один вид работы дважды.",
                    400,
                )
            seen.add(kind)
            if work.get("id") is not None:
                _uuid(work["id"])

    def create(self, payload, actor_id, actor_role):
        self._check_works(payload)
        return self._order(self._request(
            "POST", "orders", actor_id=actor_id, actor_role=actor_role,
            payload=payload,
        ))

    def patch(self, order_id, payload, actor_id, actor_role):
        self._check_works(payload)
        return self._order(self._request(
            "PATCH", f"orders/{self._order_id(order_id)}",
            actor_id=actor_id, actor_role=actor_role, payload=payload,
        ))

    def permissions(self, order_id, actor_id, actor_role):
        return self._mapping(self._request(
            "GET", f"orders/{self._order_id(order_id)}/permissions",
            actor_id=actor_id, actor_role=actor_role,
        ))

    def transition_status(
        self, order_id, status_id, actor_id, actor_role, refusal_reason=""
    ):
        if not isinstance(refusal_reason, str):
            raise OneCOrderError("invalid_refusal", "Причина отказа должна быть текстом.", 400)
        return self._order(self._request(
            "POST", f"orders/{self._order_id(order_id)}/transition-status",
            actor_id=actor_id, actor_role=actor_role,
            payload={"statusId": _uuid(status_id), "refusalReason": refusal_reason},
        ))

    def transition_work_status(self, order_id, status_id, actor_id, actor_role):
        return self._order(self._request(
            "POST", f"orders/{self._order_id(order_id)}/transition-work-status",
            actor_id=actor_id, actor_role=actor_role,
            payload={"statusId": _uuid(status_id)},
        ))

    def set_payment_status(self, order_id, status_id, actor_id, actor_role):
        return self._order(self._request(
            "POST", f"orders/{self._order_id(order_id)}/payment-status",
            actor_id=actor_id, actor_role=actor_role,
            payload={"statusId": _uuid(status_id)},
        ))

    def car_orders(self, car_id, actor_id, actor_role):
        records = self._array(self._request(
            "GET", f"orders/by-car/{self._order_id(car_id)}",
            actor_id=actor_id, actor_role=actor_role,
        ))
        return [self._order(item) for item in records]

    def car_has_orders(self, car_id, actor_id, actor_role):
        data = self._mapping(self._request(
            "GET", f"orders/car/{self._order_id(car_id)}/exists",
            actor_id=actor_id, actor_role=actor_role,
        ))
        if not isinstance(data.get("hasOrders"), bool):
            raise OneCOrderError("invalid_response", "1С не вернула признак заказов.")
        return data["hasOrders"]
