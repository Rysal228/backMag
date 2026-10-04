import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from users.models import CustomUser


class CarBrand(models.Model):

    class Meta:
        verbose_name = 'Марка автомобиля'
        verbose_name_plural = 'Марки автомобилей'

    name = models.CharField(
        max_length=100,
        unique=True,
    )

    def __str__(self):
        return self.name


class CarModel(models.Model):

    class Meta:
        verbose_name = 'Модели автомобилей'
        verbose_name_plural = 'Модели автомобилей'
        unique_together = ('brand', 'name')

    brand = models.ForeignKey(
        CarBrand,
        on_delete=models.CASCADE,
        related_name='models',
    )

    name = models.CharField(max_length=100)

    def __str__(self):
        return f'{self.brand.name} {self.name}'


class Car(models.Model):

    class Meta:
        verbose_name = 'Автомобиль'
        verbose_name_plural = 'Автомобили'
        constraints = [
            models.UniqueConstraint(
                condition=Q(vin__isnull=False),
                fields=('vin',),
                name='unique_car_vin',
            ),
        ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    owner = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='cars',
    )

    brand = models.ForeignKey(
        CarBrand,
        on_delete=models.PROTECT,
        related_name='cars',
    )

    model = models.ForeignKey(
        CarModel,
        on_delete=models.PROTECT,
        related_name='cars',
    )

    year = models.PositiveIntegerField()

    vin = models.CharField(
        max_length=64,
        null=True,
        blank=True,
    )

    plate_number = models.CharField(
        max_length=20,
        null=True,
        blank=True,
    )

    photo = models.ImageField(
        upload_to='cars/',
        null=True,
        blank=True,
    )

    is_archived = models.BooleanField(
        default=False,
        verbose_name='Архивный',
    )

    def __str__(self):
        return f'{self.brand} {self.model} ({self.plate_number})'

    def clean(self):
        if (
            self.brand_id
            and self.model_id
            and self.model.brand_id != self.brand_id
        ):
            raise ValidationError(
                'Выбранная модель не относится к указанной марке.'
            )

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)


class CarOwnership(models.Model):

    class Meta:
        verbose_name = 'История владения автомобилем'
        verbose_name_plural = 'История владения автомобилями'
        ordering = ('-started_at',)
        constraints = [
            models.UniqueConstraint(
                condition=Q(ended_at__isnull=True),
                fields=('car',),
                name='unique_current_car_ownership',
            ),
        ]

    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )

    car = models.ForeignKey(
        Car,
        on_delete=models.CASCADE,
        related_name='ownership_history',
    )

    owner = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='car_ownerships',
    )

    started_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'{self.car} — {self.owner}'
