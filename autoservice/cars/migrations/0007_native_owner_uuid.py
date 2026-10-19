from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("cars", "0006_remove_car_vin_uniqueness"),
    ]

    operations = [
        # All existing cars and ownership rows must be cleared explicitly
        # before applying: legacy user UUIDs are not 1C UUIDs.
        migrations.RemoveField(model_name="carownership", name="owner"),
        migrations.RemoveField(model_name="car", name="owner"),
        migrations.AddField(
            model_name="carownership", name="owner_id",
            field=models.UUIDField(db_index=True),
        ),
        migrations.AddField(
            model_name="car", name="owner_id",
            field=models.UUIDField(db_index=True),
        ),
    ]
