from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.services.onec import OneCIntegrationError, get_profile_connection_status


class OneCTestConnectionView(APIView):
    """Authenticated backend proxy for the configured 1C test endpoint."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        try:
            result = get_profile_connection_status()
        except OneCIntegrationError as exc:
            return Response(
                {
                    "code": exc.code,
                    "message": exc.message,
                    "details": exc.details,
                },
                status=exc.status_code or status.HTTP_502_BAD_GATEWAY,
            )

        return Response(result, status=status.HTTP_200_OK)
