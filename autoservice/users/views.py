"""Read users from 1C; logout refresh tokens without ORM application users."""
from uuid import UUID

from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.services.onec_users import OneCUsersClient
from users.models import UserRole
from users.onec_profile_views import OneCProfileView
from users.auth.tokens import revoke_refresh_token


class UserListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if request.query_params.get('role') != UserRole.MECHANIC:
            # Only the 1C roster exists. Never fall back to a Django user table.
            raise ValidationError({
                'role': 'Поддерживается только список специалистов (role=mechanic).',
            })
        current = OneCUsersClient().get_user_by_onec_id(request.user.pk)
        OneCProfileView._check_identity(request, current)
        search = request.query_params.get('search', '').strip()
        ids = [value.strip() for value in
               request.query_params.get('ids', '').split(',')
               if value.strip()]
        return Response(OneCUsersClient().list_mechanics(search=search, ids=ids))


class UserDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, user_id):
        # Only managers may inspect a different user's phone/name.
        if request.active_role != UserRole.ADMIN and user_id != request.user.id:
            raise PermissionDenied('Нет доступа к данным другого пользователя.')
        profile = OneCUsersClient().get_user_by_onec_id(user_id)
        return Response({
            'id': profile['onecId'],
            'phone': profile['phone'],
            'firstName': profile.get('firstName', ''),
            'lastName': profile.get('lastName', ''),
            'patronymic': profile.get('patronymic', ''),
            'birthday': profile.get('birthday'),
        })


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        raw = request.data.get('refreshToken')
        if not isinstance(raw, str) or not raw:
            raise ValidationError({'refreshToken': 'Refresh token is required.'})
        revoke_refresh_token(raw, user=request.user, access_token=request.auth)
        return Response(status=status.HTTP_204_NO_CONTENT)
