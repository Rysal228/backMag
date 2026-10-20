"""Drop legacy vehicle tables after orders stop referencing Django Car."""
from django.db import migrations


def require_empty_cars(apps, schema_editor):
    Car = apps.get_model("cars", "Car")
    if Car.objects.using(schema_editor.connection.alias).exists():
        raise RuntimeError(
            "В Django остались автомобили. Перед удалением таблиц "
            "перенесите или явно очистите эти записи."
        )


class Migration(migrations.Migration):
    dependencies = [
        ("cars", "0007_native_owner_uuid"),
        ("orders", "0030_native_onec_car_uuid"),
    ]

    operations = [
        migrations.RunPython(require_empty_cars, migrations.RunPython.noop),
        migrations.DeleteModel(name="CarOwnership"),
        migrations.DeleteModel(name="Car"),
        migrations.DeleteModel(name="CarModel"),
        migrations.DeleteModel(name="CarBrand"),
    ]
