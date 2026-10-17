"""Read/write user profiles through 1C; never persist profile data in Django."""

import os
from urllib.parse import quote

import requests
from rest_framework.exceptions import APIException


DEFAULT_BASE_URL = "http://host.docker.internal:8081"
DEFAULT_USERS_PATH = "/ServiceCar/hs/api/user"


class OneCUserServiceError(APIException):
    status_code = 502
    default_detail = "Не удалось получить данные пользователя из 1С."
    default_code = "onec_user_error"

    def __init__(self, code, message, *, status_code=502):
        self.status_code = status_code
        super().__init__(detail=message, code=code)


class OneCUsersClient:
    """Server-to-server API. Only a trusted, explicit internal opt-in permits no auth."""

    def __init__(self):
        self.base_url = os.environ.get("ONEC_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        self.path = os.environ.get("ONEC_USERS_PATH", DEFAULT_USERS_PATH).strip("/")
        self.api_user = os.environ.get("ONEC_API_USER")
        self.api_password = os.environ.get("ONEC_API_PASSWORD")
        self.allow_internal = (
            os.environ.get("ONEC_ALLOW_UNAUTHENTICATED_INTERNAL") == "1"
        )
        self.timeout = 10

        if bool(self.api_user) != bool(self.api_password):
            raise OneCUserServiceError(
                "onec_credentials_invalid",
                "Учётные данные интеграции 1С настроены неполностью.",
                status_code=503,
            )
        if not self.api_user and not (
            self.allow_internal and self.base_url == DEFAULT_BASE_URL
        ):
            raise OneCUserServiceError(
                "onec_credentials_missing",
                "Не настроен защищённый доступ Django к 1С.",
                status_code=503,
            )

    def _request(self, method, phone, payload=None):
        normalized = str(phone).strip().removeprefix("+")
        if not (
            len(normalized) == 11 and normalized.startswith("7")
            and normalized.isascii() and normalized.isdigit()
        ):
            raise OneCUserServiceError(
                "onec_invalid_identity",
                "Некорректный телефон учётной записи.",
                status_code=502,
            )

        url = f"{self.base_url}/{self.path}/{quote(normalized, safe='')}"
        auth = (self.api_user, self.api_password) if self.api_user else None
        try:
            response = requests.request(
                method, url, json=payload, auth=auth,
                headers={"Accept": "application/json"},
                timeout=self.timeout,
                allow_redirects=False,
            )
        except requests.Timeout as exc:
            raise OneCUserServiceError(
                "onec_timeout", "1С не ответила вовремя.", status_code=504
            ) from exc
        except requests.RequestException as exc:
            raise OneCUserServiceError(
                "onec_unavailable", "Нет соединения с 1С."
            ) from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise OneCUserServiceError(
                "onec_invalid_response", "1С вернула некорректный ответ."
            ) from exc

        if not isinstance(body, dict):
            raise OneCUserServiceError(
                "onec_invalid_response", "1С вернула некорректный ответ."
            )

        if not response.ok:
            # 1C remains authoritative for business validation.
            code = body.get("code")
            message = body.get("message")
            if response.status_code in (400, 409) and isinstance(code, str) and isinstance(message, str):
                raise OneCUserServiceError(
                    code, message, status_code=response.status_code
                )
            if response.status_code == 404:
                raise OneCUserServiceError(
                    "onec_user_not_found",
                    "Пользователь не найден в 1С.",
                    status_code=404,
                )
            # Do not expose 1C internals, especially on 500.
            raise OneCUserServiceError(
                "onec_http_error",
                "Ошибка HTTP-сервиса 1С. Проверьте состояние через GET.",
            )

        user = body.get("user")
        if not isinstance(user, dict) or not isinstance(user.get("roles"), list):
            raise OneCUserServiceError(
                "onec_invalid_response", "1С вернула некорректный профиль."
            )
        if not isinstance(user.get("externalId"), str) or not isinstance(user.get("phone"), str):
            raise OneCUserServiceError(
                "onec_invalid_response", "1С не вернула идентификатор пользователя."
            )
        return user

    def get_user(self, phone):
        return self._request("GET", phone)

    def patch_user(self, phone, data):
        return self._request("PATCH", phone, payload=data)
