"""Seed settings from existing env flags once, preserving current rollout."""
import os

from django.db import migrations, models
import django.core.validators


def seed_existing_settings(apps, schema_editor):
    model = apps.get_model('notifications', 'MaxNotificationSettings')
    enabled = lambda name: os.environ.get(name, 'false').lower() in ('1', 'true', 'yes')
    url = (
        os.environ.get('MAX_ORDER_NOTIFICATIONS_PUBLIC_URL', '').strip().rstrip('/')
        or os.environ.get('MAX_NEWS_NOTIFICATIONS_PUBLIC_URL', '').strip().rstrip('/')
    )
    model.objects.using(schema_editor.connection.alias).get_or_create(
        pk=1,
        defaults={
            'orders_enabled': enabled('MAX_ORDER_NOTIFICATIONS_ENABLED'),
            'news_enabled': enabled('MAX_NEWS_NOTIFICATIONS_ENABLED'),
            'site_url': url,
        },
    )


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name='MaxNotificationSettings',
            fields=[
                ('id', models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ('orders_enabled', models.BooleanField(default=False, help_text='Если выключено, опрос заказов и отправка очереди приостанавливаются.', verbose_name='Уведомления о статусах заказов')),
                ('news_enabled', models.BooleanField(default=False, help_text='Если выключено, новые публикации сохраняются в очереди до включения.', verbose_name='Уведомления о новых публикациях')),
                ('site_url', models.URLField(blank=True, help_text='Например: https://www.cherser-car.site. Если пусто, ссылки не добавляются.', max_length=255, verbose_name='Адрес сайта для ссылок')),
                ('send_limit', models.PositiveSmallIntegerField(default=100, help_text='Лимит для каждой фоновой команды (от 1 до 1000).', validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(1000)], verbose_name='Сообщений за запуск')),
                ('max_attempts', models.PositiveSmallIntegerField(default=5, help_text='Число попыток при временной ошибке MAX (от 1 до 10).', validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(10)], verbose_name='Попыток доставки')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Последнее изменение')),
            ],
            options={'verbose_name': 'Настройки уведомлений MAX', 'verbose_name_plural': 'Настройки уведомлений MAX'},
        ),
        migrations.AddConstraint(
            model_name='maxnotificationsettings',
            constraint=models.CheckConstraint(
                condition=models.Q(pk=1), name='max_notification_settings_singleton',
            ),
        ),
        migrations.RunPython(seed_existing_settings, migrations.RunPython.noop),
    ]
