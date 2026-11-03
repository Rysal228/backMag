"""Technical payment journal for a future licensed provider integration.

1C remains the source of truth for order and payment status. The tables
below must never be treated as proof of bank settlement without a verified
provider event or an authenticated provider-side status lookup.
"""
from uuid import uuid4

from django.db import models
from django.db.models import Q


class PaymentAttempt(models.Model):
    class State(models.TextChoices):
        DRAFT = "draft", "Подготовлен"
        PENDING = "pending", "Ожидает подтверждения"
        SUCCEEDED = "succeeded", "Подтверждён провайдером"
        FAILED = "failed", "Ошибка"
        CANCELED = "canceled", "Отменён"
        REFUNDED = "refunded", "Возвращён"

    order_id = models.UUIDField(db_index=True, verbose_name="UUID заказа в 1С")
    customer_id = models.UUIDField(db_index=True, verbose_name="UUID клиента в 1С")
    provider = models.CharField(max_length=40, default="yookassa", verbose_name="Провайдер")
    provider_payment_id = models.CharField(max_length=128, blank=True, verbose_name="ID операции провайдера")
    idempotency_key = models.UUIDField(default=uuid4, editable=False, unique=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, verbose_name="Сумма зафиксированного счёта")
    currency = models.CharField(max_length=3, default="RUB", verbose_name="Валюта")
    status = models.CharField(max_length=16, choices=State.choices, default=State.DRAFT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        verbose_name = "Попытка оплаты"
        verbose_name_plural = "Попытки оплаты"
        constraints = [
            models.CheckConstraint(condition=Q(amount__gt=0), name="payment_attempt_positive_amount"),
            models.UniqueConstraint(
                fields=("provider", "provider_payment_id"),
                condition=~Q(provider_payment_id=""),
                name="payment_provider_reference_unique",
            ),
        ]

    def __str__(self):
        return f"{self.order_id}: {self.status}"


class PaymentEvent(models.Model):
    """Deduplication metadata only: never store card details or raw webhook body."""

    provider = models.CharField(max_length=40)
    provider_event_id = models.CharField(max_length=160)
    payload_sha256 = models.CharField(max_length=64)
    payment = models.ForeignKey(
        PaymentAttempt, on_delete=models.PROTECT, related_name="events", null=True, blank=True,
    )
    received_at = models.DateTimeField(auto_now_add=True)
    verified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Событие платежа"
        verbose_name_plural = "События платежей"
        constraints = [
            models.UniqueConstraint(fields=("provider", "provider_event_id"), name="payment_event_deduplication"),
        ]
