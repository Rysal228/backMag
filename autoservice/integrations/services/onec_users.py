"""Read/write user profiles through 1C; never persist profile data in Django."""

import os
from uuid import UUID
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
        self.default_code = code
        super().__init__(detail=message, code=code)


class OneCUsersClient:
    """Server-to-server API, using the existing known internal ServiceCarAPI."""

    def __init__(self):
        self.base_url = os.environ.get("ONEC_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        self.path = os.environ.get("ONEC_USERS_PATH", DEFAULT_USERS_PATH).strip("/")
        self.api_user = os.environ.get("ONEC_API_USER")
        self.api_password = os.environ.get("ONEC_API_PASSWORD")
        # The already-published internal ServiceCarAPI needs no new
        # Django deployment flag. Custom/noninternal endpoints still require
        # configured service credentials.
        self.allow_internal = self.base_url == DEFAULT_BASE_URL
        self.timeout = 10

        if bool(self.api_user) != bool(self.api_password):
            raise OneCUserServiceError(
                "onec_credentials_invalid",
                "Учётные данные интеграции 1С настроены неполностью.",
                status_code=503,
            )
        if not self.api_user and not (
            self.allow_internal
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
        return self._request_user_url(method, url, payload=payload)

    def _request_user_url(self, method, url, payload=None):
        """Single response/error handling path for phone and native-ID lookup."""
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

    def create_user_with_password(
        self, *, phone, external_id, password, first_name, last_name,
        patronymic="", birthday=None, messenger_user_id="", roles=None,
    ):
        """Create the 1C catalog element, roles and password in one 1C transaction.

        Existing import POST /user without a password stays compatible.
        No password hash is stored in Django or returned by 1C.
        """
        normalized = str(phone).strip().removeprefix("+")
        if not (
            len(normalized) == 11 and normalized.startswith("7")
            and normalized.isascii() and normalized.isdigit()
        ):
            raise OneCUserServiceError(
                "onec_invalid_identity", "Некорректный телефон регистрации.",
                status_code=400,
            )
        native_django_id = str(UUID(str(external_id)))
        assigned_roles = sorted(set(roles if roles is not None else ["user"]))
        if not assigned_roles or not set(assigned_roles).issubset(
            {"user", "mechanic", "admin"}
        ):
            raise OneCUserServiceError(
                "onec_invalid_roles", "Некорректные роли пользователя.",
                status_code=400,
            )
        payload = {
            "phone": normalized,
            "externalId": native_django_id,
            "password": password,
            "firstName": first_name,
            "lastName": last_name,
            "patronymic": patronymic,
            "birthday": birthday.isoformat() if birthday else None,
            "isActive": True,
            "roles": assigned_roles,
        }
        if messenger_user_id:
            payload["messengerUserId"] = str(messenger_user_id)
        # The real POST response must confirm the persisted password. An old
        # 1C module without password support does not return hasPassword.
        url = f"{self.base_url}/{self.path}"
        profile = self._request_user_url("POST", url, payload=payload)
        try:
            onec_id = str(UUID(str(profile["onecId"])))
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise OneCUserServiceError(
                "onec_invalid_response", "1С не вернула собственный ID пользователя."
            ) from exc
        if (
            profile.get("phone") != normalized
            or profile.get("externalId") != native_django_id
            or profile.get("isActive") is not True
            or sorted(profile.get("roles", [])) != assigned_roles
            or profile.get("hasPassword") is not True
            or (messenger_user_id and
                profile.get("messengerUserId") != str(messenger_user_id))
        ):
            raise OneCUserServiceError(
                "onec_identity_mismatch", "1С вернула несовпадающую учётную запись."
            )
        return onec_id

    def get_user(self, phone):
        return self._request("GET", phone)

    def patch_user(self, phone, data):
        return self._request("PATCH", phone, payload=data)

    def get_user_by_onec_id(self, onec_id):
        """Fetch a 1C user using the intrinsic catalog-reference UUID, not phone."""
        try:
            native_id = str(UUID(str(onec_id)))
        except (ValueError, TypeError, AttributeError) as exc:
            raise OneCUserServiceError(
                "onec_invalid_identity", "Некорректный идентификатор 1С.",
                status_code=400,
            ) from exc

        url = f"{self.base_url}/{self.path}/id/{native_id}"
        user = self._request_user_url("GET", url)
        try:
            returned_native_id = UUID(str(user.get("onecId", "")))
        except (TypeError, ValueError, AttributeError) as exc:
            raise OneCUserServiceError(
                "onec_invalid_response", "1С не вернула идентификатор ссылки."
            ) from exc
        if str(returned_native_id) != native_id:
            raise OneCUserServiceError(
                "onec_identity_mismatch", "Ответ 1С не соответствует запросу."
            )
        return user


    def list_mechanics(self, *, search="", ids=()):
        """Read only the mechanics roster; 1C performs role/search/ID selection."""
        url = f"{self.base_url}/{self.path.rsplit('/', 1)[0]}/users/mechanics"
        auth = (self.api_user, self.api_password) if self.api_user else None
        params = {"search": search, "ids": ",".join(ids)}
        try:
            response = requests.request(
                "GET", url, params=params, auth=auth,
                headers={"Accept": "application/json"},
                timeout=self.timeout, allow_redirects=False,
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
                "onec_invalid_response", "1С вернула некорректный список специалистов."
            ) from exc

        if not response.ok:
            if (response.status_code == 400 and isinstance(body, dict)
                    and isinstance(body.get("code"), str)
                    and isinstance(body.get("message"), str)):
                raise OneCUserServiceError(
                    body["code"], body["message"], status_code=400
                )
            raise OneCUserServiceError(
                "onec_list_failed", "Ошибка получения списка специалистов из 1С."
            )

        if not isinstance(body, list) or len(body) > 20:
            raise OneCUserServiceError(
                "onec_invalid_response", "1С вернула некорректный список специалистов."
            )
        for user in body:
            if (not isinstance(user, dict)
                    or any(not isinstance(user.get(field), str)
                           for field in ("id", "phone", "firstName",
                                         "lastName", "patronymic"))
                    or user.get("birthday") is not None
                    and not isinstance(user.get("birthday"), str)):
                raise OneCUserServiceError(
                    "onec_invalid_response",
                    "1С вернула некорректную запись специалиста."
                )
        return body
