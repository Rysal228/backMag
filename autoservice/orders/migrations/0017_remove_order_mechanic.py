from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0016_order_mechanics'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='order',
            name='mechanic',
        ),
        migrations.AlterField(
            model_name='order',
            name='mechanics',
            field=models.ManyToManyField(
                blank=True,
                related_name='assigned_orders',
                to='users.customuser',
                verbose_name='Специалисты',
            ),
        ),
    ]
