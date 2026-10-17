"""Password verification through a dedicated, authenticated TLS endpoint in 1C.

Not wired into public Django login until the 1C credential store, protected
publication and rate limiting have been validated. No local password hashes.
"""

import os
from urllib.parse import urlsplit
from uuid import UUID

import requests

from integrations.services.onec_users import OneCUserServiceError


class OneCPasswordAuthClient:
    def __init__(self):
        self.url = os.environ.get("ONEC_AUTH_VERIFY_URL", "").strip()
        self.username = os.environ.get("ONEC_AUTH_API_USER", "")
        self.password = os.environ.get("ONEC_AUTH_API_PASSWORD", "")
        parts = urlsplit(self.url)

        # Fail closed: the existing unauthenticated HTTP integration is not
        # acceptable for transferring plaintext passwords over the network.
        if (
            parts.scheme != "https" or not parts.hostname
            or parts.username is not None or parts.password is not None
            or parts.query or parts.fragment
        ):
            raise OneCUserServiceError(
                "onec_auth_tls_required",
                "Не настроен защищённый HTTPS-адрес авторизации 1С.",
                status_code=503,
            )

        if not self.username or not self.password:
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
                auth=(self.username, self.password),
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
