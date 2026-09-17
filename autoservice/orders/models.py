import uuid

from django.core.exceptions import ValidationError
from django.db import models

from users.models import CustomUser
from cars.models import Car


class StatusAppearance(models.TextChoices):
    POSITIVE = 'positive', 'Положительный'
    WARNING = 'warning', 'Предупреждение'
    NEGATIVE = 'negative', 'Отрицательный'


class WorkType(models.Model):
    class Meta:
        verbose_name = 'Тип работ'
        verbose_name_plural = 'Типы работ'

    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class OrderStatus(models.Model):
    class Meta:
        verbose_name = 'Статус заказа'
        verbose_name_plural = 'Статусы заказов'

    name = models.CharField(max_length=100, unique=True)
    appearance = models.CharField(
        verbose_name='Внешний вид статуса',
        max_length=20,
        choices=StatusAppearance.choices,
        default=StatusAppearance.WARNING,
    )
    is_initial = models.BooleanField(verbose_name='Начальный статус', default=False)
    requires_payment = models.BooleanField(verbose_name='Требует оплаты', default=False)

    def clean(self):
        if self.is_initial and OrderStatus.objects.filter(is_initial=True).exclude(pk=self.pk).exists():
            raise ValidationError({'is_initial': 'Начальный статус заказа уже настроен.'})

    def __str__(self):
        return self.name


class WorkStatus(models.Model):
    class Meta:
        verbose_name = 'Статус работы'
        verbose_name_plural = 'Статусы работ'

    name = models.CharField(max_length=100, unique=True)
    appearance = models.CharField(
        verbose_name='Внешний вид статуса',
        max_length=20,
        choices=StatusAppearance.choices,
        default=StatusAppearance.WARNING,
    )

    def __str__(self):
        return self.name


class Order(models.Model):
    class Meta:
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order_number = models.CharField(max_length=50, unique=True)
    customer = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='orders')
    car = models.ForeignKey(Car, on_delete=models.PROTECT, related_name='orders')
    work_type = models.ForeignKey(WorkType, on_delete=models.PROTECT)
    status = models.ForeignKey(OrderStatus, on_delete=models.PROTECT)
    work_status = models.ForeignKey(WorkStatus, on_delete=models.PROTECT, null=True, blank=True)
    appointment_at = models.DateTimeField(null=True, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    def clean(self):
        if self.customer_id and self.car_id and self.car.owner_id != self.customer_id:
            raise ValidationError('Автомобиль не принадлежит выбранному клиенту.')

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
