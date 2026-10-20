"""Explicit cutover: orders must be empty before dropping the old Car FK."""
from django.db import migrations, models


def require_empty_orders(apps, schema_editor):
    Order = apps.get_model("orders", "Order")
    if Order.objects.using(schema_editor.connection.alias).exists():
        raise RuntimeError(
            "Нельзя переводить заказы на UUID автомобилей 1С при наличии старых заказов. "
            "Перенесите их в 1С или явно очистите учебные данные до migrate."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0029_native_user_uuids"),
        ("cars", "0007_native_owner_uuid"),
    ]

    operations = [
        migrations.RunPython(require_empty_orders, migrations.RunPython.noop),
        migrations.RemoveField(model_name="order", name="car"),
        migrations.AddField(
            model_name="order", name="car_id",
            field=models.UUIDField(db_index=True),
        ),
        migrations.AddField(
            model_name="order", name="car_brand_id",
            field=models.UUIDField(db_index=True),
        ),
        migrations.AddField(
            model_name="order", name="car_model_id",
            field=models.UUIDField(db_index=True),
        ),
    ]
