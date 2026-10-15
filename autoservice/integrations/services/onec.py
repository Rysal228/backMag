import logging
import os
from urllib.parse import urljoin

import requests


logger = logging.getLogger(__name__)

ONEC_BASE_URL = os.environ.get("ONEC_BASE_URL", "http://host.docker.internal:8081").rstrip("/")
ONEC_PROFILE_PATH = os.environ.get(
    "ONEC_PROFILE_PATH",
    "/ServiceCar/hs/api/user/profile",
)
ONEC_TIMEOUT_SECONDS = 10


class OneCIntegrationError(Exception):
    """Base exception for errors while communicating with 1C."""

    def __init__(self, code, message, *, status_code=None, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details


def _response_payload(response):
    try:
        return response.json()
    except ValueError:
        return {"raw": response.text[:4000]}


def get_profile_connection_status():
    """Call the configured 1C profile endpoint and return a normalized result."""
    url = urljoin(f"{ONEC_BASE_URL}/", ONEC_PROFILE_PATH.lstrip("/"))

    try:
        response = requests.get(
            url,
            timeout=ONEC_TIMEOUT_SECONDS,
            headers={"Accept": "application/json"},
        )
    except requests.Timeout as exc:
        raise OneCIntegrationError(
            "onec_timeout",
            "Сервис 1С не ответил за отведённое время.",
            status_code=504,
        ) from exc
    except requests.RequestException as exc:
        logger.exception("Could not reach the configured 1C profile endpoint")
        raise OneCIntegrationError(
            "onec_unavailable",
            "Не удалось связаться с сервисом 1С.",
            status_code=502,
        ) from exc

    payload = _response_payload(response)

    if not response.ok:
        raise OneCIntegrationError(
            "onec_http_error",
            "Сервис 1С вернул ошибку.",
            status_code=502,
            details={"status": response.status_code, "response": payload},
        )

    return {
        "code": "ok",
        "message": "Ответ от сервиса 1С получен.",
        "details": {
            "status": response.status_code,
            "response": payload,
        },
    }
