from django.db import migrations, models
import django.db.models.deletion


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
    ]
