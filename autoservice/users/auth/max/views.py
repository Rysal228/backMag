from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import MaxAuthSerializer
from .services import MaxAuthService


class MaxAuthView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = MaxAuthSerializer(
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        tokens = MaxAuthService.authenticate(
            **serializer.validated_data,
        )

        return Response(
            tokens,
            status=status.HTTP_200_OK,
        )