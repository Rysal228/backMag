from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .role_selection_views import RoleSelectionView
from .serializers import (
    LoginSerializer,
    PasswordSerializer,
    RefreshTokenSerializer,
    RegisterSerializer,
    RoleSerializer,
)
from .services import AuthService


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        tokens = AuthService.login(
            phone=serializer.validated_data['phone'],
            password=serializer.validated_data['password'],
            role=serializer.validated_data.get('role'),
        )

        return Response(
            tokens,
            status=status.HTTP_200_OK,
        )


class RoleSelectionEndpointView(RoleSelectionView):
    pass


class SwitchRoleView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = RoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        tokens = AuthService.switch_role(
            user=request.user,
            role=serializer.validated_data['role'],
            token=request.auth,
        )

        return Response(tokens, status=status.HTTP_200_OK)


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        tokens = AuthService.register(
            **serializer.validated_data,
        )

        return Response(
            tokens,
            status=status.HTTP_201_CREATED,
        )


class PasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            'hasPassword': request.user.has_usable_password(),
        })

    def post(self, request):
        serializer = PasswordSerializer(
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        AuthService.set_password(
            user=request.user,
            current_password=serializer.validated_data.get('currentPassword'),
            new_password=serializer.validated_data['newPassword'],
        )

        return Response(
            status=status.HTTP_204_NO_CONTENT,
        )


class RefreshTokenView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RefreshTokenSerializer(
            data=request.data,
        )

        serializer.is_valid(
            raise_exception=True,
        )

        return Response(
            serializer.validated_data,
            status=status.HTTP_200_OK,
        )
