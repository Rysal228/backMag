from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0014_order_work_types'),
    ]

    operations = [
        migrations.AlterField(
            model_name='order',
            name='work_types',
            field=models.ManyToManyField(
                related_name='orders',
                to='orders.worktype',
            ),
        ),
    ]
