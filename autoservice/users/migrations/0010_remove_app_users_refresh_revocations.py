"""Drop legacy application-user tables after migrating domain UUID relations.

IMPORTANT: This schema is for a new/empty test PostgreSQL database.
The change from AUTH_USER_MODEL=users.CustomUser to auth.User cannot safely
be applied to an existing populated database without rebuilding its schema.
"""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0009_customuser_onec_id"),
        ("cars", "0007_native_owner_uuid"),
        ("orders", "0029_native_user_uuids"),
        ("chats", "0004_native_chat_participant_uuids"),
    ]

    operations = [
        migrations.DeleteModel(name="MaxAuthCode"),
        migrations.DeleteModel(name="UserRoleAssignment"),
        migrations.DeleteModel(name="CustomUser"),
        migrations.CreateModel(
            name="RevokedRefreshToken",
            fields=[
                ("jti", models.UUIDField(editable=False, primary_key=True, serialize=False)),
                ("expires_at", models.DateTimeField(db_index=True)),
            ],
            options={
                "verbose_name": "Отозванный refresh-токен",
                "verbose_name_plural": "Отозванные refresh-токены",
            },
        ),
    ]
