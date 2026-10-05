import uuid

from django.db import migrations


def migrate_order_numbers(apps, schema_editor):
    Order = apps.get_model('orders', 'Order')
    existing_numbers = set(Order.objects.values_list('order_number', flat=True))

    for order in Order.objects.order_by('created_at', 'id'):
        while True:
            order_number = f'ORD-{order.created_at:%Y%m%d}-{uuid.uuid4().hex[:6].upper()}'
            if order_number not in existing_numbers:
                break

        Order.objects.filter(pk=order.pk).update(order_number=order_number)
        existing_numbers.add(order_number)


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('orders', '0010_order_vehicle_snapshots'),
    ]

    operations = [
        migrations.RunPython(migrate_order_numbers, noop),
    ]
