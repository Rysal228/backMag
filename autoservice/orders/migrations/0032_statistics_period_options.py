"""Manager statistics period presets, configured in Django Admin."""
import django.core.validators
from django.db import migrations, models
from django.db.models import Q


def seed_statistics_periods(apps, schema_editor):
    Period = apps.get_model("orders", "StatisticsPeriodOption")
    for days in (7, 30, 90):
        Period.objects.using(schema_editor.connection.alias).get_or_create(
            days=days,
            defaults={"enabled": True, "is_default": days == 30},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0031_orders_state_to_onec"),
    ]

    operations = [
        migrations.CreateModel(
            name="StatisticsPeriodOption",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("days", models.PositiveSmallIntegerField(
                    help_text="От 1 до 90 дней. Более длинный период не поддерживается 1С.",
                    unique=True,
                    validators=[
                        django.core.validators.MinValueValidator(1),
                        django.core.validators.MaxValueValidator(90),
                    ],
                    verbose_name="Длительность, дней",
                )),
                ("enabled", models.BooleanField(default=True, verbose_name="Показывать в статистике")),
                ("is_default", models.BooleanField(
                    default=False,
                    help_text="Только один период может быть выбран по умолчанию.",
                    verbose_name="По умолчанию",
                )),
            ],
            options={
                "ordering": ("days",),
                "verbose_name": "Период статистики",
                "verbose_name_plural": "Периоды статистики",
            },
        ),
        migrations.AddConstraint(
            model_name="statisticsperiodoption",
            constraint=models.UniqueConstraint(
                condition=Q(is_default=True),
                fields=("is_default",),
                name="single_statistics_default_period",
            ),
        ),
        migrations.RunPython(seed_statistics_periods, migrations.RunPython.noop),
    ]
