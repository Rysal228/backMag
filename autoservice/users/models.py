"""Only operational auth records live in PostgreSQL; 1C owns users."""
from django.db import models


class UserRole(models.TextChoices):
    USER = "user", "Пользователь"
    MECHANIC = "mechanic", "Механик"
    ADMIN = "admin", "Администратор"


class ConsumedRefreshToken(models.Model):
    """Single-use refresh-token JTI for rotation and logout, no user ForeignKey."""
    jti = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Использованный refresh-токен"
        verbose_name_plural = "Использованные refresh-токены"
