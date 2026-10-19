"""Only server-owned auth metadata is stored here, never application users."""
from django.db import models


class UserRole(models.TextChoices):
    USER = 'user', 'Пользователь'
    MECHANIC = 'mechanic', 'Механик'
    ADMIN = 'admin', 'Администратор'


class RevokedRefreshToken(models.Model):
    """JTI tombstone for rotation and logout; no application-user foreign key."""

    jti = models.UUIDField(primary_key=True, editable=False)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        verbose_name = 'Отозванный refresh-токен'
        verbose_name_plural = 'Отозванные refresh-токены'
