"""Drop the obsolete app-user schema after all domain FKs have been replaced.

Requires a controlled fresh/test database rebuild; do not run against
uncleared business data or a populated legacy JWT blacklist.
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
        migrations.CreateModel(
            name="ConsumedRefreshToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("jti", models.CharField(max_length=64, unique=True)),
                ("expires_at", models.DateTimeField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Использованный refresh-токен",
                "verbose_name_plural": "Использованные refresh-токены",
            },
        ),
        migrations.DeleteModel(name="MaxAuthCode"),
        migrations.DeleteModel(name="UserRoleAssignment"),
        migrations.DeleteModel(name="CustomUser"),
    ]
