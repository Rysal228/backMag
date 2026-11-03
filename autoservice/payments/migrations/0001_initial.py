# Generated for the payment foundation. No payment operations are created.
import uuid
from django.db import migrations, models
from django.db.models import Q
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="PaymentAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("order_id", models.UUIDField(db_index=True, verbose_name="UUID заказа в 1С")),
                ("customer_id", models.UUIDField(db_index=True, verbose_name="UUID клиента в 1С")),
                ("provider", models.CharField(default="yookassa", max_length=40, verbose_name="Провайдер")),
                ("provider_payment_id", models.CharField(blank=True, max_length=128, verbose_name="ID операции провайдера")),
                ("idempotency_key", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("amount", models.DecimalField(decimal_places=2, max_digits=12, verbose_name="Сумма зафиксированного счёта")),
                ("currency", models.CharField(default="RUB", max_length=3, verbose_name="Валюта")),
                ("status", models.CharField(choices=[
                    ("draft", "Подготовлен"), ("pending", "Ожидает подтверждения"),
                    ("succeeded", "Подтверждён провайдером"), ("failed", "Ошибка"),
                    ("canceled", "Отменён"), ("refunded", "Возвращён"),
                ], default="draft", max_length=16)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ("-created_at",), "verbose_name": "Попытка оплаты", "verbose_name_plural": "Попытки оплаты"},
        ),
        migrations.CreateModel(
            name="PaymentEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(max_length=40)),
                ("provider_event_id", models.CharField(max_length=160)),
                ("payload_sha256", models.CharField(max_length=64)),
                ("received_at", models.DateTimeField(auto_now_add=True)),
                ("verified_at", models.DateTimeField(blank=True, null=True)),
                ("payment", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="events", to="payments.paymentattempt")),
            ],
            options={"verbose_name": "Событие платежа", "verbose_name_plural": "События платежей"},
        ),
        migrations.AddConstraint(model_name="paymentattempt", constraint=models.CheckConstraint(condition=Q(amount__gt=0), name="payment_attempt_positive_amount")),
        migrations.AddConstraint(model_name="paymentattempt", constraint=models.UniqueConstraint(fields=("provider", "provider_payment_id"), condition=~Q(provider_payment_id=""), name="payment_provider_reference_unique")),
        migrations.AddConstraint(model_name="paymentevent", constraint=models.UniqueConstraint(fields=("provider", "provider_event_id"), name="payment_event_deduplication")),
    ]
