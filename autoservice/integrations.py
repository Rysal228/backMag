import logging
import os

import requests
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView


logger = logging.getLogger(__name__)

ONEC_TEST_URL = os.environ.get(
    "ONEC_TEST_URL",
    "http://host.docker.internal:8081/ServiceCar/hs/api/user/profile",
)
ONEC_TIMEOUT_SECONDS = 10


class OneCTestConnectionView(APIView):
    """Authenticated backend proxy for the configured 1C test endpoint."""

    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = None  # Use the project's default DRF authentication classes.

    def get(self, request):
        try:
            response = requests.get(
                ONEC_TEST_URL,
                timeout=ONEC_TIMEOUT_SECONDS,
                headers={"Accept": "application/json"},
            )
        except requests.Timeout:
            return Response(
                {
                    "code": "onec_timeout",
                    "message": "Сервис 1С не ответил за отведённое время.",
                    "details": None,
                },
                status=status.HTTP_504_GATEWAY_TIMEOUT,
            )
        except requests.RequestException:
            logger.exception("Could not reach the configured 1C test endpoint")
            return Response(
                {
                    "code": "onec_unavailable",
                    "message": "Не удалось связаться с сервисом 1С.",
                    "details": None,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        try:
            payload = response.json()
        except ValueError:
            payload = {"raw": response.text[:4000]}

        if not response.ok:
            return Response(
                {
                    "code": "onec_http_error",
                    "message": "Сервис 1С вернул ошибку.",
                    "details": {
                        "status": response.status_code,
                        "response": payload,
                    },
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response(
            {
                "code": "ok",
                "message": "Ответ от сервиса 1С получен.",
                "details": {
                    "status": response.status_code,
                    "response": payload,
                },
            },
            status=status.HTTP_200_OK,
        )
