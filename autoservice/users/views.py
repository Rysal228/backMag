from rest_framework import viewsets, permissions, status
from rest_framework.exceptions import ValidationError
from .models import UserRole
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError

from .serializers import (
    CustomUserSerializer,
    ProfileCustomUserSerializer,
)


User = get_user_model()


class CustomUserViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = User.objects.all()
    serializer_class = CustomUserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = super().get_queryset()

        role = self.request.query_params.get('role')

        if not role:
            return queryset

        if role not in UserRole.values:
            raise ValidationError({
                'role': 'Invalid user role.',
            })

        return queryset.filter(role=role)

class ProfileCustomUserView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = ProfileCustomUserSerializer(request.user)

        return Response({
            'user': serializer.data,
        })

    def patch(self, request):
        serializer = ProfileCustomUserSerializer(
            request.user,
            data=request.data,
            partial=True,
        )

        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({
            'user': serializer.data,
        })

class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refreshToken')

        if not refresh_token:
            return Response(
                {
                    'detail': 'Refresh token is required.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            return Response(
                {
                    'detail': 'Invalid refresh token.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            status=status.HTTP_204_NO_CONTENT,
        )