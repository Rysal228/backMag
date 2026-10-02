from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .serializers import (
    MaxAuthSerializer,
    MaxCodeRequestSerializer,
    MaxCodeVerifySerializer,
)
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


class MaxCodeRequestView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = MaxCodeRequestSerializer(
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        MaxAuthService.request_code(
            **serializer.validated_data,
        )

        return Response(
            {'message': 'Код отправлен в MAX.'},
            status=status.HTTP_200_OK,
        )


class MaxCodeVerifyView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = MaxCodeVerifySerializer(
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        tokens = MaxAuthService.verify_code(
            **serializer.validated_data,
        )

        return Response(
            tokens,
            status=status.HTTP_200_OK,
        )
