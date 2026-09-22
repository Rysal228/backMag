from rest_framework import permissions, viewsets

from .models import News
from .serializers import NewsSerializer


class NewsViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = NewsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        role = self.request.user.role

        return (
            News.objects
            .filter(
                models.Q(is_global=True)
                | models.Q(role_targets__role=role),
            )
            .prefetch_related('role_targets')
            .distinct()
        )
