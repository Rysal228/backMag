"""Only presentation filter permissions are stored in Django.

Orders, statuses, works, payments and booking records are native 1C data.
"""
from django.db import models
from users.models import UserRole


class OrderFilterKey(models.TextChoices):
    SEARCH = 'search', 'Поиск'
    ORDER_NUMBER = 'order_number', 'Номер заказа'
    VIN = 'vin', 'VIN'
    PLATE_NUMBER = 'plate_number', 'Государственный номер'
    BRAND = 'brand', 'Марка'
    MODEL = 'model', 'Модель'
    WORK_TYPE = 'work_type', 'Тип работ'
    STATUS = 'status', 'Статус заказа'
    WORK_STATUS = 'work_status', 'Статус работы'
    DATE_RANGE = 'date_range', 'Период'


class OrderFilterPermission(models.Model):
    class Meta:
        verbose_name = 'Доступ к фильтру заказа'
        verbose_name_plural = 'Доступ к фильтрам заказов'
        constraints = [
            models.UniqueConstraint(
                fields=('role', 'filter_key'),
                name='unique_order_filter_permission',
            ),
        ]

    role = models.CharField(
        verbose_name='Роль',
        max_length=20,
        choices=UserRole.choices,
    )
    filter_key = models.CharField(
        verbose_name='Фильтр',
        max_length=30,
        choices=OrderFilterKey.choices,
    )
    enabled = models.BooleanField(verbose_name='Разрешён', default=True)

    def __str__(self):
        return f'{self.get_role_display()}: {self.get_filter_key_display()}'
