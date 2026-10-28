"""1C user roster and application logout; no Django user-table reads."""
from rest_framework import permissions, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.services.onec_users import OneCUsersClient
from .models import UserRole
from .auth.token_rotation import logout_refresh


class UserListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if request.query_params.get("role") != UserRole.MECHANIC:
            raise ValidationError({
                "role": "Поддерживается только список специалистов из 1С.",
            })
        search = request.query_params.get("search", "").strip()
        ids = [x.strip() for x in request.query_params.get("ids", "").split(",") if x.strip()]
        if search == "*":
            # The full roster is a manager-only picker mode. Existing targeted
            # searches remain available for previously authorized workflows.
            if request.active_role != UserRole.ADMIN:
                raise PermissionDenied("Полный список специалистов доступен только менеджеру.")
            return Response(OneCUsersClient().list_mechanics(
                search=search, ids=ids,
                actor_id=request.user.id, actor_role=request.active_role,
            ))
        return Response(OneCUsersClient().list_mechanics(search=search, ids=ids))


class LogoutView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refreshToken")
        if not isinstance(refresh, str) or not refresh:
            raise ValidationError({"refreshToken": "Refresh-токен обязателен."})
        logout_refresh(refresh, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
