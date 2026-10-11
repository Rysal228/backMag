from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('cars', '0004_car_ownership'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='carmodel',
            options={
                'verbose_name': 'Модели автомобилей',
                'verbose_name_plural': 'Модели автомобилей',
                'unique_together': {('brand', 'name')},
            },
        ),
    ]
