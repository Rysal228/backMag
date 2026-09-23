from django.db.models import Q
from rest_framework import permissions, viewsets
from rest_framework.pagination import LimitOffsetPagination

from users.models import UserRole

from .models import News
from .serializers import NewsSerializer


ROLE_ACCESS: dict[UserRole, tuple[UserRole, ...]] = {
    UserRole.USER: (
        UserRole.USER,
    ),
    UserRole.MECHANIC: (
        UserRole.USER,
        UserRole.MECHANIC,
    ),
    UserRole.ADMIN: (
        UserRole.USER,
        UserRole.MECHANIC,
        UserRole.ADMIN,
    ),
}


class NewsPagination(LimitOffsetPagination):
    default_limit = 10
    max_limit = 50


class NewsViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NewsSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = NewsPagination

    def get_queryset(self):
        role = self.request.user.role
        accessible_roles = ROLE_ACCESS.get(role, (role,))

        return (
            News.objects
            .filter(
                Q(is_global=True)
                | Q(role_targets__role__in=accessible_roles),
            )
            .prefetch_related('role_targets')
            .order_by('-created_at', '-id')
            .distinct()
        )
