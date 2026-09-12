import uuid

from django.db import models
from django.contrib.auth.models import AbstractUser

from .managers import CustomUserManager


# class CustomUser(AbstractUser):
#     id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
#     messenger_user_id = models.CharField(max_length=255,unique=True,null=True,blank=True)
#     full_name = models.CharField(verbose_name="ФИО", max_length=250, null=True, blank=True)
#     phone = models.CharField(verbose_name="Номер телефона", max_length=20, unique=True)
#     birthday = models.DateField(verbose_name="Дата рождения",null=True,blank=True)
#
#     USERNAME_FIELD = 'phone'
#     REQUIRED_FIELDS = ['username']
#
#     objects = CustomUserManager()
#
#     def __str__(self):
#         return self.phone

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

    full_name = models.CharField(
        verbose_name='ФИО',
        max_length=250,
        null=True,
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

    USERNAME_FIELD = 'phone'
    REQUIRED_FIELDS = []

    objects = CustomUserManager()