from rest_framework import serializers

from .models import News


class NewsSerializer(serializers.ModelSerializer):
    createdAt = serializers.DateTimeField(
        source='created_at',
        read_only=True,
    )
    updatedAt = serializers.DateTimeField(
        source='updated_at',
        read_only=True,
    )
    roles = serializers.SerializerMethodField()

    class Meta:
        model = News
        fields = (
            'id',
            'title',
            'content',
            'image',
            'is_global',
            'roles',
            'createdAt',
            'updatedAt',
        )

    def get_roles(self, obj):
        return list(
            obj.role_targets.values_list('role', flat=True)
        )
