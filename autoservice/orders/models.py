"""Only presentation filter permissions are stored in Django.

Orders, statuses, works, payments and booking records are native 1C data.
"""
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone
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
            # Non-field error: Django Admin's list-editable form excludes is_default.
            raise ValidationError("Период по умолчанию должен быть включён.")

    def __str__(self):
        return f"{self.days} дн." + (" (по умолчанию)" if self.is_default else "")


class OrderNotificationSnapshot(models.Model):
    """Most recently observed 1C state, not the order source of truth."""

    order_id = models.UUIDField(primary_key=True, serialize=False)
    car_id = models.UUIDField()
    owner_id = models.UUIDField()
    order_code = models.CharField(max_length=80)
    work_code = models.CharField(max_length=80, blank=True)
    revision = models.PositiveIntegerField(default=0)
    observed_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Снимок статусов заказа для MAX"
        verbose_name_plural = "Снимки статусов заказов для MAX"


class OrderNotificationDelivery(models.Model):
    """Durable outgoing notification; never store phone or MAX user id."""

    class State(models.TextChoices):
        PENDING = "pending", "В очереди"
        SENT = "sent", "Отправлено"
        SKIPPED = "skipped", "Нет действующей привязки MAX"
        FAILED = "failed", "Не доставлено"

    order_id = models.UUIDField(db_index=True)
    car_id = models.UUIDField()
    owner_id = models.UUIDField()
    revision = models.PositiveIntegerField()
    order_number = models.CharField(max_length=100)
    car_name = models.CharField(max_length=180)
    order_code = models.CharField(max_length=80)
    work_code = models.CharField(max_length=80, blank=True)
    order_label = models.CharField(max_length=120, blank=True)
    work_label = models.CharField(max_length=120, blank=True)
    order_changed = models.BooleanField(default=False)
    work_changed = models.BooleanField(default=False)
    state = models.CharField(max_length=12, choices=State.choices, default=State.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("created_at", "id")
        verbose_name = "MAX-уведомление о заказе"
        verbose_name_plural = "MAX-уведомления о заказах"
        constraints = [
            models.UniqueConstraint(
                fields=("order_id", "revision"),
                name="unique_order_max_notification_revision",
            ),
        ]
