from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('cars', '0004_car_ownership'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='car',
            name='unique_car_owner_vin',
        ),
    ]
