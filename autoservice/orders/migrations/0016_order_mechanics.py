from django.db import migrations, models


def copy_mechanics_to_many_to_many(apps, schema_editor):
    Order = apps.get_model('orders', 'Order')

    for order in Order.objects.exclude(mechanic_id=None).iterator():
        order.mechanics.add(order.mechanic_id)


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0015_alter_order_work_types'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='mechanics',
            field=models.ManyToManyField(
                blank=True,
                related_name='assigned_orders_many',
                to='users.customuser',
            ),
        ),
        migrations.RunPython(
            copy_mechanics_to_many_to_many,
            migrations.RunPython.noop,
        ),
    ]
