"""Only presentation filter permissions are stored in Django.

Orders, statuses, works, payments and booking records are native 1C data.
"""
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
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


class StatisticsPeriodOption(models.Model):
    """Django-managed choices shown on the manager statistics page.

    The 1C statistics endpoint supports a maximum of 90 inclusive days.
    No order/appointment data is stored in this table.
    """

    days = models.PositiveSmallIntegerField(
        verbose_name="Длительность, дней",
        unique=True,
        validators=[MinValueValidator(1), MaxValueValidator(90)],
        help_text="От 1 до 90 дней. Более длинный период не поддерживается 1С.",
    )
    enabled = models.BooleanField(verbose_name="Показывать в статистике", default=True)
    is_default = models.BooleanField(
        verbose_name="По умолчанию", default=False,
        help_text="Только один период может быть выбран по умолчанию.",
    )

    class Meta:
        ordering = ("days",)
        verbose_name = "Период статистики"
        verbose_name_plural = "Периоды статистики"
        constraints = [
            models.UniqueConstraint(
                fields=("is_default",),
                condition=models.Q(is_default=True),
                name="single_statistics_default_period",
            ),
        ]

    def clean(self):
        super().clean()
        if self.is_default and not self.enabled:
            raise ValidationError({
                "is_default": "Период по умолчанию должен быть включён.",
            })

    def __str__(self):
        return f"{self.days} дн." + (" (по умолчанию)" if self.is_default else "")
