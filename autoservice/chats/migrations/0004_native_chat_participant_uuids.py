from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("chats", "0003_private_chat_attachment_storage"),
        ("orders", "0029_native_user_uuids"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="chatroom", name="chat_room_type_mechanic_consistency",
        ),
        migrations.RemoveConstraint(
            model_name="chatroom", name="unique_manager_mechanic_chat_per_order",
        ),
        migrations.RemoveField(model_name="chatmessage", name="sender"),
        migrations.RemoveField(model_name="chatroom", name="mechanic"),
        migrations.AddField(
            model_name="chatmessage", name="sender_id",
            field=models.UUIDField(db_index=True),
        ),
        migrations.AddField(
            model_name="chatroom", name="mechanic_id",
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
        migrations.AddConstraint(
            model_name="chatroom",
            constraint=models.CheckConstraint(
                condition=(
                    Q(type="customer_manager", mechanic_id__isnull=True)
                    | Q(type="manager_mechanic", mechanic_id__isnull=False)
                ),
                name="chat_room_type_mechanic_consistency",
            ),
        ),
        migrations.AddConstraint(
            model_name="chatroom",
            constraint=models.UniqueConstraint(
                fields=("order", "mechanic_id"),
                condition=Q(type="manager_mechanic"),
                name="unique_manager_mechanic_chat_per_order",
            ),
        ),
    ]
