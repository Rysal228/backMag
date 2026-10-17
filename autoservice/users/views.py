from rest_framework import viewsets, permissions, status
from rest_framework.exceptions import ValidationError
from .models import UserRole
from integrations.services.onec_users import OneCUsersClient
from .onec_profile_views import OneCProfileView
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.response import Response
from rest_framework_simplejwt.exceptions import TokenError

from .serializers import CustomUserSerializer


User = get_user_model()


class CustomUserViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = User.objects.all()
    serializer_class = CustomUserSerializer
    permission_classes = [permissions.IsAuthenticated]

    def list(self, request, *args, **kwargs):
        # The mechanics roster always comes from 1C. Other user lists are transitional.
        if request.query_params.get('role') == UserRole.MECHANIC:
            client = OneCUsersClient()
            current = client.get_user(request.user.phone)
            OneCProfileView._check_identity(request, current)
            search = request.query_params.get('search', '').strip()
            ids = [value.strip() for value in
                   request.query_params.get('ids', '').split(',')
                   if value.strip()]
            return Response(client.list_mechanics(search=search, ids=ids))

        return super().list(request, *args, **kwargs)

    def get_queryset(self):
        queryset = super().get_queryset()

        role = self.request.query_params.get('role')

        if not role:
            return queryset

        if role not in UserRole.values:
            raise ValidationError({
                'role': 'Invalid user role.',
            })

        # Never expose a stale local mechanics record via a detail lookup.
        if role == UserRole.MECHANIC:
            return queryset.none()

        return queryset.filter(role_assignments__role=role).distinct()


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh_token = request.data.get('refreshToken')

        if not refresh_token:
            raise ValidationError({
                'refreshToken': 'Refresh token is required.',
            })

        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
        except TokenError:
            raise ValidationError({
                'refreshToken': 'Invalid refresh token.',
            })

        return Response(
            status=status.HTTP_204_NO_CONTENT,
        )
