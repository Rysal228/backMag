"""HTTP client for MAX business operations in the existing 1C ServiceCarAPI.

Django validates MAX initData and contact signatures before sending identity
claims to the 1C HTTP service. This uses the same backend-to-Apache connection
as the existing user API; no additional Basic-auth credentials are required.
Keep ServiceCarAPI reachable only through the existing trusted deployment
network while these handlers have no independent caller authentication.
"""

import os
from uuid import UUID

import requests
from rest_framework.exceptions import APIException


class OneCMaxError(APIException):
    status_code = 502
    default_code = "onec_max_unavailable"
    default_detail = "Не удалось выполнить операцию MAX в 1С."

    def __init__(self, code, detail, *, status_code=502):
        self.status_code = status_code
        self.default_code = code
        super().__init__(detail=detail, code=code)


# Use the same base URL as the existing 1C user API.
DEFAULT_ONEC_BASE_URL = "http://host.docker.internal:8081"
MAX_HTTP_PATH = "/ServiceCar/hs/api"


class OneCMaxClient:
    def __init__(self):
        # No separate MAX environment variables or technical user credentials.
        # The existing backend -> Apache HTTP publication handles this route.
        self.base_url = (
            os.environ.get("ONEC_BASE_URL", DEFAULT_ONEC_BASE_URL).strip().rstrip("/")
            + MAX_HTTP_PATH
        )

    def _post(self, path, payload):
        try:
            response = requests.post(
                f"{self.base_url}/max/{path}",
                json=payload,
                headers={"Accept": "application/json"},
                timeout=10,
                allow_redirects=False,
            )
        except requests.Timeout as exc:
            raise OneCMaxError(
                "onec_max_timeout", "Сервер 1С не ответил вовремя.",
                status_code=504,
            ) from exc
        except requests.RequestException as exc:
            raise OneCMaxError(
                "onec_max_unavailable", "Недоступна авторизация MAX в 1С."
            ) from exc

        try:
            result = response.json()
        except ValueError as exc:
            raise OneCMaxError(
                "onec_max_bad_response", "Некорректный ответ MAX-сервиса 1С."
            ) from exc

        if not isinstance(result, dict):
            raise OneCMaxError(
                "onec_max_bad_response", "Некорректный ответ MAX-сервиса 1С."
            )

        if response.status_code != 200:
            code = result.get("code")
            # Do not expose untrusted upstream error text; only known codes.
            if response.status_code == 409 and code == "max_account_conflict":
                raise OneCMaxError(
                    "max_account_conflict",
                    "Этот номер телефона или аккаунт MAX уже связан с другой учётной записью.",
                    status_code=409,
                )
            if response.status_code == 429 and code == "max_code_throttled":
                raise OneCMaxError(
                    "max_code_throttled",
                    "Повторно запросить код можно через 60 секунд.",
                    status_code=429,
                )
            if response.status_code == 401 and code in ("max_not_available", "user_inactive"):
                raise OneCMaxError(
                    code, "Авторизация MAX недоступна для этого пользователя.",
                    status_code=401,
                )
            raise OneCMaxError(
                "onec_max_upstream_error", "Ошибка MAX-сервиса 1С."
            )
        return result

    @staticmethod
    def _profile(data):
        if not isinstance(data, dict):
            raise OneCMaxError(
                "onec_max_bad_response", "1С не вернула пользователя."
            )
        try:
            onec_id = str(UUID(str(data["onecId"])))
            phone = data["phone"]
            messenger_user_id = data["messengerUserId"]
            roles = data["roles"]
            active = data["isActive"]
            first_name = data.get("firstName", "")
            last_name = data.get("lastName", "")
        except (KeyError, TypeError, ValueError, AttributeError) as exc:
            raise OneCMaxError(
                "onec_max_bad_response", "1С вернула некорректные идентификаторы."
            ) from exc
        if (
            not isinstance(phone, str) or len(phone) != 11
            or not phone.startswith("7") or not phone.isascii() or not phone.isdigit()
            or not isinstance(messenger_user_id, str) or not messenger_user_id.isascii()
            or not messenger_user_id.isdigit() or not 1 <= len(messenger_user_id) <= 20
            or type(active) is not bool
            or not isinstance(roles, list) or not roles
            or any(not isinstance(item, str) for item in roles)
            or len(roles) != len(set(roles))
            or not set(roles) <= {"user", "mechanic", "admin"}
            or not isinstance(first_name, str) or not isinstance(last_name, str)
            or len(first_name) > 150 or len(last_name) > 150
        ):
            raise OneCMaxError(
                "onec_max_bad_response", "1С вернула некорректный профиль."
            )
        if not active:
            raise OneCMaxError(
                "max_user_inactive", "Пользователь неактивен.", status_code=401,
            )
        return {
            "onecId": onec_id,
            "phone": phone,
            "messengerUserId": messenger_user_id,
            "roles": roles,
            "isActive": True,
            "firstName": first_name,
            "lastName": last_name,
        }

    def resolve(self, *, messenger_user_id, phone=None,
                first_name="", last_name=""):
        payload = {"messengerUserId": str(messenger_user_id)}
        if phone is not None:
            payload.update({
                "phone": str(phone),
                "firstName": first_name,
                "lastName": last_name,
            })
        response = self._post("resolve", payload)
        if response.get("status") == "contact_required" and len(response) == 1:
            return None
        if response.get("status") != "ok":
            raise OneCMaxError("onec_max_bad_response", "Некорректный результат авторизации.")
        return self._profile(response.get("user"))

    def issue_code(self, *, phone, code, request_id):
        response = self._post(
            "code/issue", {"phone": phone, "code": code, "requestId": str(request_id)},
        )
        messenger_id = response.get("messengerUserId")
        if (
            response.get("issued") is not True
            or not isinstance(messenger_id, str)
            or not messenger_id.isascii() or not messenger_id.isdigit()
        ):
            raise OneCMaxError("onec_max_bad_response", "1С не подтвердила выдачу кода.")
        return messenger_id

    def cancel_code(self, *, phone, request_id):
        response = self._post("code/cancel", {
            "phone": phone, "requestId": str(request_id),
        })
        if response.get("cancelled") is not True:
            raise OneCMaxError("onec_max_bad_response", "1С не подтвердила отмену кода.")

    def verify_code(self, *, phone, code):
        response = self._post("code/verify", {"phone": phone, "code": code})
        if response.get("authenticated") is True:
            return self._profile(response.get("user")), None
        reason = response.get("reason")
        if response.get("authenticated") is not False or reason not in {
            "invalid", "used", "expired", "attempts",
        }:
            raise OneCMaxError("onec_max_bad_response", "Некорректный ответ проверки кода.")
        return None, reason
