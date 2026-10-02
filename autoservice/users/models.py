import uuid

from django.db import models
from django.contrib.auth.models import AbstractUser

from .managers import CustomUserManager


class UserRole(models.TextChoices):
    USER = 'user', 'Пользователь'
    MECHANIC = 'mechanic', 'Механик'
    ADMIN = 'admin', 'Администратор'


class CustomUser(AbstractUser):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    username = models.CharField(
        max_length=150,
        unique=True,
        null=True,
        blank=True,
    )

    messenger_user_id = models.CharField(
        max_length=255,
        unique=True,
        null=True,
        blank=True,
    )

    patronymic = models.CharField(
        verbose_name='Отчество',
        max_length=150,
        blank=True,
    )

    phone = models.CharField(
        verbose_name='Номер телефона',
        max_length=20,
        unique=True,
    )

    birthday = models.DateField(
        verbose_name='Дата рождения',
        null=True,
        blank=True,
    )

    role = models.CharField(
        verbose_name='Роль',
        max_length=20,
        choices=UserRole.choices,
        default=UserRole.USER,
    )

    USERNAME_FIELD = 'phone'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()

    def get_full_name(self) -> str:
        return ' '.join(
            part
            for part in (
                self.last_name,
                self.first_name,
                self.patronymic,
            )
            if part
        )


class MaxAuthCode(models.Model):
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='max_auth_codes',
    )
    code_hash = models.CharField(max_length=128)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(
                fields=['user', '-created_at'],
                name='max_auth_code_user_created_idx',
            ),
        ]
