from rest_framework import serializers

from users.models import UserRole


class RoleSelectionSerializer(serializers.Serializer):
    selectionToken = serializers.CharField(
        source='selection_token',
        write_only=True,
    )
    role = serializers.ChoiceField(
        choices=UserRole.choices,
    )
