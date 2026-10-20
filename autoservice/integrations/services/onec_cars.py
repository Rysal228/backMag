"""Only gateway for 1C vehicle catalogs. No Django car models or fallback reads."""
import os
from uuid import UUID
from urllib.parse import quote

import requests
from rest_framework.exceptions import APIException

from integrations.services.onec_users import DEFAULT_BASE_URL


def canonical_uuid(value):
    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise OneCCarError("invalid_id", "Некорректный идентификатор 1С.", 400) from exc


class OneCCarError(APIException):
    status_code = 502
    default_detail = "Ошибка сервиса автомобилей 1С."
    default_code = "onec_car_error"

    def __init__(self, code, message, status_code=502):
        self.status_code = status_code
        super().__init__(detail=message, code=code)


class OneCCarsClient:
    def __init__(self):
        self.base = os.environ.get("ONEC_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        self.path = os.environ.get("ONEC_CARS_PATH", "/ServiceCar/hs/api").strip("/")
        self.user = os.environ.get("ONEC_API_USER")
        self.password = os.environ.get("ONEC_API_PASSWORD")
        # Match OneCUsersClient: the existing local 1C publication may use
        # the internal network without Basic Auth. Never allow this exception
        # for a different/custom 1C endpoint.
        self.allow_internal = self.base == DEFAULT_BASE_URL
        if bool(self.user) != bool(self.password):
            raise OneCCarError(
                "onec_credentials_invalid",
                "Учётные данные интеграции 1С настроены неполностью.",
                503,
            )
        if not self.user and not self.allow_internal:
            raise OneCCarError(
                "onec_credentials_missing",
                "Не настроен защищённый доступ Django к 1С.",
                503,
            )

    def _call(self, method, resource, identifier=None, *, params=None, payload=None):
        url = f"{self.base}/{self.path}/{resource}"
        if identifier is not None:
            url += "/" + quote(canonical_uuid(identifier), safe="")
        try:
            response = requests.request(
                method, url, params=params, json=payload,
                auth=(self.user, self.password) if self.user else None,
                headers={"Accept": "application/json"},
                timeout=10, allow_redirects=False,
            )
        except requests.Timeout as exc:
            raise OneCCarError("onec_timeout", "1С не ответила вовремя.", 504) from exc
        except requests.RequestException as exc:
            raise OneCCarError("onec_unavailable", "Нет соединения с 1С.") from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise OneCCarError("invalid_response", "1С вернула некорректный JSON.") from exc
        if not response.ok:
            if (response.status_code in (400, 404, 409)
                and isinstance(body, dict)
                and isinstance(body.get("message"), str)):
                raise OneCCarError(body.get("code", "onec_validation"), body["message"],
                                  response.status_code)
            raise OneCCarError("onec_http_error", "Сервис автомобилей 1С вернул ошибку.")
        return body

    @staticmethod
    def _catalog_item(value, kind):
        if not isinstance(value, dict) or not isinstance(value.get("name"), str):
            raise OneCCarError("invalid_response", "1С вернула некорректный элемент справочника.")
        canonical_uuid(value.get("id"))
        if kind == "models":
            canonical_uuid(value.get("brand"))
        return value

    def brands(self):
        items = self._call("GET", "car-brands")
        if not isinstance(items, list):
            raise OneCCarError("invalid_response", "1С вернула некорректный список марок.")
        return [self._catalog_item(item, "brands") for item in items]

    def models(self, brand=None):
        params = {"brand": canonical_uuid(brand)} if brand else None
        items = self._call("GET", "car-models", params=params)
        if not isinstance(items, list):
            raise OneCCarError("invalid_response", "1С вернула некорректный список моделей.")
        return [self._catalog_item(item, "models") for item in items]

    @staticmethod
    def _vehicle(value):
        if not isinstance(value, dict):
            raise OneCCarError("invalid_response", "1С вернула некорректный автомобиль.")
        for field in ("id", "ownerId", "brand", "model"):
            canonical_uuid(value.get(field))
        if value.get("status") not in ("active", "archived"):
            raise OneCCarError("invalid_response", "1С вернула некорректный статус автомобиля.")
        if any(not isinstance(value.get(field), str) for field in ("brandName", "modelName")):
            raise OneCCarError("invalid_response", "1С вернула некорректные наименования.")
        if not isinstance(value.get("year"), int) or isinstance(value["year"], bool):
            raise OneCCarError("invalid_response", "1С вернула некорректный год.")
        return value

    def list_cars(self, owner=None):
        params = {"owner": canonical_uuid(owner)} if owner else None
        result = self._call("GET", "cars", params=params)
        if not isinstance(result, list):
            raise OneCCarError("invalid_response", "1С вернула некорректный список автомобилей.")
        return [self._vehicle(v) for v in result]

    def get(self, car_id):
        car_id = canonical_uuid(car_id)
        result = self._vehicle(self._call("GET", "cars", car_id))
        if canonical_uuid(result["id"]) != car_id:
            raise OneCCarError("identity_mismatch", "1С вернула другой автомобиль.")
        return result

    def create(self, fields):
        return self._vehicle(self._call("POST", "cars", payload=fields))

    def patch(self, car_id, fields):
        return self._vehicle(self._call("PATCH", "cars", car_id, payload=fields))

    def archive(self, car_id):
        return self._vehicle(self._call("DELETE", "cars", car_id))

    def restore(self, car_id):
        car_id = canonical_uuid(car_id)
        result = self._call("POST", f"cars/{car_id}/restore")
        return self._vehicle(result)
