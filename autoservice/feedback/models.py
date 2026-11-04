"""Customer satisfaction is local Django data; 1C retains order ownership and status."""
from uuid import uuid4

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class FeedbackOrderSnapshot(models.Model):
    """Last observed 1C order state, used to detect a *new* terminal transition."""

    order_id = models.UUIDField(primary_key=True, serialize=False)
    car_id = models.UUIDField()
    owner_id = models.UUIDField()
    order_code = models.CharField(max_length=80)
    observed_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Снимок заказа для опросов'
        verbose_name_plural = 'Снимки заказов для опросов'


class FeedbackInvitation(models.Model):
    class State(models.TextChoices):
        PENDING = 'pending', 'Ожидает отправки'
        SENT = 'sent', 'Отправлено'
        SKIPPED = 'skipped', 'Пропущено'
        FAILED = 'failed', 'Ошибка доставки'
        DECLINED = 'declined', 'Клиент отказался'

    # One invitation per order even if the 1C record is subsequently modified.
    order_id = models.UUIDField(unique=True)
    car_id = models.UUIDField()
    owner_id = models.UUIDField()
    outcome = models.CharField(max_length=20, choices=[
        ('closed', 'Автомобиль выдан'), ('cancelled', 'Заказ отменён'),
    ])
    order_number = models.CharField(max_length=100)
    car_name = models.CharField(max_length=180)
    token = models.UUIDField(unique=True, default=uuid4, editable=False)
    state = models.CharField(max_length=12, choices=State.choices, default=State.PENDING)
    due_at = models.DateTimeField(db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-created_at', '-pk')
        verbose_name = 'MAX-запрос оценки'
        verbose_name_plural = 'MAX-запросы оценок'

    def __str__(self):
        return f'Заказ №{self.order_number}'


class FeedbackResponse(models.Model):
    class Reason(models.TextChoices):
        QUALITY = 'quality', 'Качество работ'
        TIMING = 'timing', 'Сроки'
        PRICE = 'price', 'Стоимость'
        COMMUNICATION = 'communication', 'Общение'
        CUSTOMER_CANCEL = 'customer_cancel', 'Отменил по личным причинам'
        OTHER = 'other', 'Другая причина'

    invitation = models.OneToOneField(
        FeedbackInvitation, on_delete=models.PROTECT, related_name='response',
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name='Оценка',
    )
    reason = models.CharField(
        max_length=24, blank=True, choices=Reason.choices,
        verbose_name='Причина',
    )
    comment = models.TextField(blank=True, verbose_name='Комментарий')
    responded_at = models.DateTimeField(auto_now_add=True)
    comment_user_digest = models.CharField(max_length=64, blank=True, db_index=True)
    comment_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ('-responded_at', '-pk')
        verbose_name = 'Оценка и отзыв'
        verbose_name_plural = 'Оценки и отзывы'

    def __str__(self):
        return f'Заказ №{self.invitation.order_number}: {self.rating}/5'
