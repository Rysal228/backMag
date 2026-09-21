from datetime import timedelta

from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


def create_busy_slots(apps, schema_editor):
    Order = apps.get_model('orders', 'Order')
    BusySlot = apps.get_model('orders', 'BusySlot')
    AppointmentSettings = apps.get_model('orders', 'AppointmentSettings')

    settings = AppointmentSettings.objects.first()
    if settings is None:
        return

    duration = timedelta(minutes=settings.appointment_duration)

    for order in Order.objects.exclude(appointment_at__isnull=True):
        appointment = timezone.localtime(order.appointment_at)
        end = appointment + duration
        BusySlot.objects.get_or_create(
            order=order,
            defaults={
                'date': appointment.date(),
                'start_time': appointment.time().replace(second=0, microsecond=0),
                'end_time': end.time().replace(second=0, microsecond=0),
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ('orders', '0008_schedule_blocks'),
    ]

    operations = [
        migrations.CreateModel(
            name='BusySlot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(verbose_name='Дата')),
                ('start_time', models.TimeField(verbose_name='Начало занятого времени')),
                ('end_time', models.TimeField(verbose_name='Конец занятого времени')),
                ('order', models.OneToOneField(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='busy_slot',
                    to='orders.order',
                    verbose_name='Заказ',
                )),
            ],
            options={
                'verbose_name': 'Занятое время',
                'verbose_name_plural': 'Занятое время',
                'ordering': ('date', 'start_time'),
            },
        ),
        migrations.RunPython(create_busy_slots, migrations.RunPython.noop),
    ]
