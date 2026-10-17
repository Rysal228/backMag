# Generated for staged 1C user identity migration.
# Intentionally schema-only: NO automatic requests to 1C and NO data updates.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0008_userroleassignment"),
    ]

    operations = [
        migrations.AddField(
            model_name="customuser",
            name="onec_id",
            field=models.UUIDField(
                blank=True,
                editable=False,
                null=True,
                unique=True,
            ),
        ),
    ]
