"""Detach legacy ORM order schema without DROP TABLE or data loss.

The old tables are retained physically for archival and backfill workflows.
Django no longer maps them or reads/writes order data.
"""
from django.db import migrations


def require_exported_orders(apps, schema_editor):
    model = apps.get_model("orders", "Order")
    if model.objects.using(schema_editor.connection.alias).exists():
        raise RuntimeError(
            "В PostgreSQL остались заказы. Сначала перенесите все заказы "
            "и связи чатов в 1С с сохранением UUID, затем удалите или "
            "архивируйте исходные записи по проверенной процедуре. "
            "Миграция остановлена без удаления данных."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("orders", "0030_native_onec_car_uuid"),
        ("chats", "0005_chatroom_native_onec_order_uuid"),
    ]

    operations = [
        migrations.RunPython(require_exported_orders, migrations.RunPython.noop),
        # Remove only ORM/state mapping. Physical tables remain untouched.
        migrations.SeparateDatabaseAndState(
            database_operations=[],
            state_operations=[
                migrations.DeleteModel(name="OrderMechanic"),
                migrations.DeleteModel(name="OrderWork"),
                migrations.DeleteModel(name="BusySlot"),
                migrations.DeleteModel(name="OrderStatusTransition"),
                migrations.DeleteModel(name="WorkStatusTransition"),
                migrations.DeleteModel(name="Order"),
                migrations.DeleteModel(name="ScheduleBlock"),
                migrations.DeleteModel(name="WeekdaySchedule"),
                migrations.DeleteModel(name="AppointmentSettings"),
                migrations.DeleteModel(name="PaymentStatus"),
                migrations.DeleteModel(name="WorkStatus"),
                migrations.DeleteModel(name="OrderStatus"),
                migrations.DeleteModel(name="WorkType"),
            ],
        ),
    ]
