from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0032_statistics_period_options"),
    ]

    operations = [
        migrations.CreateModel(
            name="OrderNotificationSnapshot",
            fields=[
                ("order_id", models.UUIDField(primary_key=True, serialize=False)),
                ("car_id", models.UUIDField()),
                ("owner_id", models.UUIDField()),
                ("order_code", models.CharField(max_length=80)),
                ("work_code", models.CharField(blank=True, max_length=80)),
                ("revision", models.PositiveIntegerField(default=0)),
                ("observed_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Снимок статусов заказа для MAX",
                "verbose_name_plural": "Снимки статусов заказов для MAX",
            },
        ),
        migrations.CreateModel(
            name="OrderNotificationDelivery",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("order_id", models.UUIDField(db_index=True)),
                ("car_id", models.UUIDField()),
                ("owner_id", models.UUIDField()),
                ("revision", models.PositiveIntegerField()),
                ("order_number", models.CharField(max_length=100)),
                ("car_name", models.CharField(max_length=180)),
                ("order_code", models.CharField(max_length=80)),
                ("work_code", models.CharField(blank=True, max_length=80)),
                ("order_label", models.CharField(blank=True, max_length=120)),
                ("work_label", models.CharField(blank=True, max_length=120)),
                ("order_changed", models.BooleanField(default=False)),
                ("work_changed", models.BooleanField(default=False)),
                ("state", models.CharField(choices=[
                    ("pending", "В очереди"), ("sent", "Отправлено"),
                    ("skipped", "Нет действующей привязки MAX"), ("failed", "Не доставлено"),
                ], default="pending", max_length=12)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("next_attempt_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "ordering": ("created_at", "id"),
                "verbose_name": "MAX-уведомление о заказе",
                "verbose_name_plural": "MAX-уведомления о заказах",
            },
        ),
        migrations.AddConstraint(
            model_name="ordernotificationdelivery",
            constraint=models.UniqueConstraint(
                fields=("order_id", "revision"),
                name="unique_order_max_notification_revision",
            ),
        ),
    ]
