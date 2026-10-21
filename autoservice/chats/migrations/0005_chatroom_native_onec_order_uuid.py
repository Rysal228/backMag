"""Detach chats from Django Order FK while preserving all room order_id values."""
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("chats", "0004_native_chat_participant_uuids"),
        ("orders", "0030_native_onec_car_uuid"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="chatroom", name="unique_customer_manager_chat_per_order",
        ),
        migrations.RemoveConstraint(
            model_name="chatroom", name="unique_manager_mechanic_chat_per_order",
        ),
        # Both FK and UUIDField use the SAME physical PostgreSQL order_id.
        # AlterField removes the FK constraint; it does not copy/drop the column.
        migrations.AlterField(
            model_name="chatroom",
            name="order",
            field=models.UUIDField(
                db_column="order_id", db_index=True, verbose_name="Заказ 1С"
            ),
        ),
        migrations.RenameField(
            model_name="chatroom", old_name="order", new_name="order_id",
        ),
        migrations.AddConstraint(
            model_name="chatroom",
            constraint=models.UniqueConstraint(
                fields=("order_id",),
                condition=Q(type="customer_manager"),
                name="unique_customer_manager_chat_per_order",
            ),
        ),
        migrations.AddConstraint(
            model_name="chatroom",
            constraint=models.UniqueConstraint(
                fields=("order_id", "mechanic_id"),
                condition=Q(type="manager_mechanic"),
                name="unique_manager_mechanic_chat_per_order",
            ),
        ),
    ]
