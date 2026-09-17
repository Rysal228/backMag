from django.db import migrations


def set_default_status_appearances(apps, schema_editor):
    OrderStatus = apps.get_model('orders', 'OrderStatus')
    WorkStatus = apps.get_model('orders', 'WorkStatus')

    OrderStatus.objects.filter(name__in=['Оплачен', 'Принят']).update(appearance='positive')
    OrderStatus.objects.filter(name__in=['Не оплачен', 'Отказано', 'Ожидание оплаты']).update(appearance='negative')
    OrderStatus.objects.filter(name='На рассмотрении').update(appearance='warning')

    WorkStatus.objects.filter(name='Выполнено').update(appearance='positive')
    WorkStatus.objects.filter(name='В работе').update(appearance='warning')


class Migration(migrations.Migration):
    dependencies = [
        ('orders', '0005_orderstatus_requires_payment'),
    ]

    operations = [
        migrations.RunPython(set_default_status_appearances, migrations.RunPython.noop),
    ]
