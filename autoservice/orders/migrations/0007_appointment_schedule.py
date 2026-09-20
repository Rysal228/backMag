from datetime import time

from django.db import migrations, models
import django.core.validators


def create_default_schedule(apps, schema_editor):
    AppointmentSettings = apps.get_model('orders', 'AppointmentSettings')
    WeekdaySchedule = apps.get_model('orders', 'WeekdaySchedule')

    AppointmentSettings.objects.get_or_create(
        id=1,
        defaults={
            'appointment_duration': 60,
            'slot_interval': 30,
        },
    )

    for weekday in range(7):
        WeekdaySchedule.objects.get_or_create(
            weekday=weekday,
            defaults={
                'is_working': weekday < 5,
                'start_time': time(9, 0) if weekday < 5 else None,
                'end_time': time(20, 0) if weekday < 5 else None,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ('orders', '0006_set_default_status_appearances'),
    ]

    operations = [
        migrations.CreateModel(
            name='AppointmentSettings',
            fields=[
                ('id', models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ('appointment_duration', models.PositiveIntegerField(
                    default=60,
                    validators=[
                        django.core.validators.MinValueValidator(5),
                        django.core.validators.MaxValueValidator(1440),
                    ],
                    verbose_name='Длительность записи, мин.',
                )),
                ('slot_interval', models.PositiveIntegerField(
                    default=30,
                    validators=[
                        django.core.validators.MinValueValidator(5),
                        django.core.validators.MaxValueValidator(1440),
                    ],
                    verbose_name='Интервал начала записи, мин.',
                )),
            ],
            options={
                'verbose_name': 'Настройки записи',
                'verbose_name_plural': 'Настройки записи',
            },
        ),
        migrations.CreateModel(
            name='ScheduleException',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('date', models.DateField(unique=True, verbose_name='Дата')),
                ('is_working', models.BooleanField(default=False, verbose_name='Рабочий день')),
                ('start_time', models.TimeField(blank=True, null=True, verbose_name='Начало рабочего времени')),
                ('end_time', models.TimeField(blank=True, null=True, verbose_name='Конец рабочего времени')),
            ],
            options={
                'verbose_name': 'Исключение расписания',
                'verbose_name_plural': 'Исключения расписания',
                'ordering': ('date',),
            },
        ),
        migrations.CreateModel(
            name='WeekdaySchedule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('weekday', models.PositiveSmallIntegerField(
                    choices=[
                        (0, 'Понедельник'),
                        (1, 'Вторник'),
                        (2, 'Среда'),
                        (3, 'Четверг'),
                        (4, 'Пятница'),
                        (5, 'Суббота'),
                        (6, 'Воскресенье'),
                    ],
                    verbose_name='День недели',
                )),
                ('is_working', models.BooleanField(default=True, verbose_name='Рабочий день')),
                ('start_time', models.TimeField(blank=True, null=True, verbose_name='Начало рабочего дня')),
                ('end_time', models.TimeField(blank=True, null=True, verbose_name='Конец рабочего дня')),
            ],
            options={
                'verbose_name': 'Расписание по дню недели',
                'verbose_name_plural': 'Расписание по дням недели',
                'ordering': ('weekday',),
            },
        ),
        migrations.AddConstraint(
            model_name='weekdayschedule',
            constraint=models.UniqueConstraint(fields=('weekday',), name='unique_weekday_schedule'),
        ),
        migrations.RunPython(create_default_schedule, migrations.RunPython.noop),
    ]
