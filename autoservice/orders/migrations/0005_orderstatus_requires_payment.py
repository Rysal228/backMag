from django.db import migrations, models


def set_initial_payment_statuses(apps, schema_editor):
    OrderStatus = apps.get_model('orders', 'OrderStatus')
    OrderStatus.objects.filter(name__in=['Не оплачен', 'Ожидание оплаты']).update(requires_payment=True)


class Migration(migrations.Migration):
    dependencies = [
        ('orders', '0004_configure_statuses'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderstatus',
            name='requires_payment',
            field=models.BooleanField(default=False, verbose_name='Требует оплаты'),
        ),
        migrations.RunPython(set_initial_payment_statuses, migrations.RunPython.noop),
    ]
