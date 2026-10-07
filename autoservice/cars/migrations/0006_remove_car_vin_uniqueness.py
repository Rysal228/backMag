from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('cars', '0005_alter_carmodel_options'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='car',
            name='unique_car_owner_vin',
        ),
    ]
