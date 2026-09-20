from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('orders', '0007_appointment_schedule'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='weekdayschedule',
            name='unique_weekday_schedule',
        ),
        migrations.DeleteModel(
            name='ScheduleException',
        ),
        migrations.CreateModel(
            name='ScheduleBlock',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(verbose_name='Дата')),
                ('start_time', models.TimeField(verbose_name='Начало недоступного интервала')),
                ('end_time', models.TimeField(verbose_name='Конец недоступного интервала')),
            ],
            options={
                'verbose_name': 'Недоступный интервал',
                'verbose_name_plural': 'Недоступные интервалы',
                'ordering': ('date', 'start_time'),
            },
        ),
        migrations.AddConstraint(
            model_name='weekdayschedule',
            constraint=models.UniqueConstraint(fields=('weekday',), name='unique_weekday_schedule'),
        ),
    ]
