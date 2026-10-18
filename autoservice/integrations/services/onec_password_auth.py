"""Password verification through existing 1C ServiceCarAPI.

By default calls the exact internal 1C URL already deployed.
The HTTP hop transmits user passwords without encryption. HTTPS may be
configured separately. No password hashes are stored by this client.
"""

import os
from urllib.parse import urlsplit
from uuid import UUID

import requests

from integrations.services.onec_users import OneCUserServiceError


# Only the already-published internal 1C endpoint can use HTTP.
# Never allow public hosts, arbitrary internal URLs or redirects via this mode.
INTERNAL_PLAINTEXT_VERIFY_URL = (
    "http://host.docker.internal:8081/ServiceCar/hs/api/password/verify"
)


class OneCPasswordAuthClient:
    def __init__(self):
        self.url = (
            os.environ.get("ONEC_AUTH_VERIFY_URL", "").strip()
            or INTERNAL_PLAINTEXT_VERIFY_URL
        )
        self.username = os.environ.get("ONEC_AUTH_API_USER", "")
        self.password = os.environ.get("ONEC_AUTH_API_PASSWORD", "")
        parts = urlsplit(self.url)

        self.internal_http = self.url == INTERNAL_PLAINTEXT_VERIFY_URL
        valid_url = (
            bool(parts.hostname)
            and parts.username is None and parts.password is None
            and not parts.query and not parts.fragment
        )
        if not valid_url or (
            parts.scheme != "https" and not self.internal_http
        ):
            raise OneCUserServiceError(
                "onec_auth_tls_required",
                "Не настроен допустимый адрес авторизации 1С.",
                status_code=503,
            )

        if self.internal_http:
            # Sending Basic credentials in plaintext is never permitted.
            if self.username or self.password:
                raise OneCUserServiceError(
                    "onec_auth_credentials_not_allowed",
                    "Не передавайте технический пароль через HTTP.",
                    status_code=503,
                )
        elif not self.username or not self.password:
            raise OneCUserServiceError(
                "onec_auth_credentials_required",
                "Не настроена техническая авторизация Django в 1С.",
                status_code=503,
            )

    def verify_password(self, *, phone, password):
        phone = str(phone).strip().removeprefix("+")
        if not (
            len(phone) == 11 and phone.startswith("7")
            and phone.isascii() and phone.isdigit()
        ):
            raise OneCUserServiceError(
                "onec_auth_invalid_phone", "Некорректный номер телефона.",
                status_code=400,
            )
        if not isinstance(password, str) or not (1 <= len(password) <= 128):
            raise OneCUserServiceError(
                "onec_auth_invalid_password", "Некорректные данные входа.",
                status_code=400,
            )

        try:
            response = requests.post(
                self.url,
                json={"phone": phone, "password": password},
                auth=None if self.internal_http else (self.username, self.password),
                headers={"Accept": "application/json"},
                timeout=10,
                allow_redirects=False,
            )
        except requests.Timeout as exc:
            raise OneCUserServiceError(
                "onec_auth_timeout", "1С не ответила вовремя.",
                status_code=504,
            ) from exc
        except requests.RequestException as exc:
            raise OneCUserServiceError(
                "onec_auth_unavailable", "Недоступен сервер авторизации 1С.",
                status_code=503,
            ) from exc

        if response.status_code != 200:
            # In particular, 401 from reverse proxy means invalid *service*
            # credentials, not a bad application-user password.
            raise OneCUserServiceError(
                "onec_auth_upstream_error",
                "Не удалось проверить учётные данные через 1С.",
                status_code=502,
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise OneCUserServiceError(
                "onec_auth_invalid_response", "Некорректный ответ авторизации 1С.",
                status_code=502,
            ) from exc

        if not isinstance(data, dict) or type(data.get("authenticated")) is not bool:
            raise OneCUserServiceError(
                "onec_auth_invalid_response", "Некорректный ответ авторизации 1С.",
                status_code=502,
            )

        if not data["authenticated"]:
            # Identical response for unknown account, missing password or
            # invalid password: the public API must not enumerate users.
            return None

        try:
            native_id = str(UUID(str(data["onecId"])))
            roles = data["roles"]
            active = data["isActive"]
            response_phone = data["phone"]
            if (
                type(active) is not bool or not active
                or response_phone != phone
                or not isinstance(roles, list) or not roles
                or not all(role in ("user", "mechanic", "admin") for role in roles)
                or len(set(roles)) != len(roles)
            ):
                raise ValueError("invalid authorization claims")
        except (KeyError, ValueError, TypeError, AttributeError) as exc:
            raise OneCUserServiceError(
                "onec_auth_invalid_response", "1С вернула неверные данные пользователя.",
                status_code=502,
            ) from exc

        return {"onecId": native_id, "phone": phone, "roles": roles}

    def change_password(self, *, phone, onec_id, current_password, new_password):
        """Change the password only after 1C verifies the existing password."""
        phone = str(phone).strip().removeprefix("+")
        if not (
            len(phone) == 11 and phone.startswith("7")
            and phone.isascii() and phone.isdigit()
        ):
            raise OneCUserServiceError(
                "onec_auth_invalid_phone", "Некорректный номер телефона.",
                status_code=400,
            )
        try:
            native_id = str(UUID(str(onec_id)))
        except (TypeError, ValueError, AttributeError) as exc:
            raise OneCUserServiceError(
                "onec_auth_invalid_identity", "Некорректная привязка к 1С.",
                status_code=403,
            ) from exc
        if (
            not isinstance(current_password, str)
            or not 1 <= len(current_password) <= 128
            or not isinstance(new_password, str)
            or not 8 <= len(new_password) <= 128
        ):
            raise OneCUserServiceError(
                "onec_auth_invalid_password", "Некорректные данные смены пароля.",
                status_code=400,
            )

        # Same exact ServiceCarAPI host and authentication policy as verify.
        # No HTTP redirect and no Basic technical credentials on internal HTTP.
        if not self.url.endswith("/password/verify"):
            raise OneCUserServiceError(
                "onec_auth_invalid_url", "Некорректный адрес сервиса 1С.",
                status_code=503,
            )
        change_url = self.url[:-len("/password/verify")] + "/password/change"
        try:
            response = requests.post(
                change_url,
                json={
                    "phone": phone,
                    "onecId": native_id,
                    "currentPassword": current_password,
                    "newPassword": new_password,
                },
                auth=None if self.internal_http else (self.username, self.password),
                headers={"Accept": "application/json"},
                timeout=10,
                allow_redirects=False,
            )
        except requests.Timeout as exc:
            raise OneCUserServiceError(
                "onec_auth_timeout", "1С не ответила вовремя.",
                status_code=504,
            ) from exc
        except requests.RequestException as exc:
            raise OneCUserServiceError(
                "onec_auth_unavailable", "Недоступен сервер паролей 1С.",
                status_code=503,
            ) from exc

        if response.status_code != 200:
            raise OneCUserServiceError(
                "onec_auth_upstream_error", "1С не смогла изменить пароль.",
                status_code=502,
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise OneCUserServiceError(
                "onec_auth_invalid_response", "Некорректный ответ сервиса 1С.",
                status_code=502,
            ) from exc
        if not isinstance(data, dict) or type(data.get("changed")) is not bool:
            raise OneCUserServiceError(
                "onec_auth_invalid_response", "Некорректный ответ сервиса 1С.",
                status_code=502,
            )
        if not data["changed"]:
            return False

        try:
            returned_id = str(UUID(str(data["onecId"])))
            returned_phone = data["phone"]
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise OneCUserServiceError(
                "onec_auth_invalid_response", "Ответ 1С не содержит пользователя.",
                status_code=502,
            ) from exc
        if returned_id != native_id or returned_phone != phone:
            raise OneCUserServiceError(
                "onec_auth_identity_mismatch", "1С вернула другого пользователя.",
                status_code=502,
            )
        return True
