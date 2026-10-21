"""Unlink chat rooms from local orders while preserving order_id UUID values."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("chats", "0004_native_chat_participant_uuids"),
        ("orders", "0030_native_onec_car_uuid"),
    ]

    operations = [
        # The old ForeignKey and new UUIDField share the SAME physical
        # PostgreSQL order_id column. AlterField removes the DB FK constraint.
        migrations.AlterField(
            model_name="chatroom",
            name="order",
            field=models.UUIDField(db_column="order_id", db_index=True, verbose_name="Заказ 1С"),
        ),
        # With an identical db_column, RenameField is a state/ORM rename,
        # not a data copy or a physical column rename.
        migrations.RenameField(
            model_name="chatroom", old_name="order", new_name="order_id",
        ),
    ]
