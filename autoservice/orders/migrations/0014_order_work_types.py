from django.db import migrations, models
import django.db.models.deletion


def copy_work_types_to_many_to_many(apps, schema_editor):
    Order = apps.get_model('orders', 'Order')

    for order in Order.objects.exclude(work_type_id=None).iterator():
        order.work_types.add(order.work_type_id)


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0013_order_mechanic'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='work_types',
            field=models.ManyToManyField(
                blank=True,
                related_name='orders',
                to='orders.worktype',
            ),
        ),
        migrations.RunPython(copy_work_types_to_many_to_many, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='order',
            name='work_type',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='orders.worktype',
            ),
        ),
    ]
