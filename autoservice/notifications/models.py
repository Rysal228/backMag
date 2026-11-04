"""Operator-controlled notification settings. Bot and 1C secrets stay in env."""
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


def normalize_site_origin(value):
    """Accept a site origin only; never build a message with an unsafe URL."""
    origin = str(value or '').strip().rstrip('/')
    if not origin:
        return ''
    try:
        parsed = urlsplit(origin)
        # Accessing .port also rejects malformed port syntax.
        _ = parsed.port
    except ValueError:
        raise ValueError('Укажите HTTPS-адрес сайта без пути, параметров и учётных данных.') from None
    if not (parsed.scheme == 'https' and parsed.hostname and not parsed.username
            and not parsed.password and not parsed.path and not parsed.query
            and not parsed.fragment):
        raise ValueError('Укажите HTTPS-адрес сайта без пути, параметров и учётных данных.')
    return origin


class MaxNotificationSettings(models.Model):
    """Single row, shared by the orders and news workers."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    orders_enabled = models.BooleanField(
        'Уведомления о статусах заказов', default=False,
        help_text='Если выключено, опрос заказов и отправка очереди приостанавливаются.',
    )
    news_enabled = models.BooleanField(
        'Уведомления о новых публикациях', default=False,
        help_text='Если выключено, новые публикации сохраняются в очереди до включения.',
    )
    site_url = models.URLField(
        'Адрес сайта для ссылок', max_length=255, blank=True,
        help_text='Например: https://www.cherser-car.site. Если пусто, ссылки не добавляются.',
    )
    send_limit = models.PositiveSmallIntegerField(
        'Сообщений за запуск', default=100,
        validators=[MinValueValidator(1), MaxValueValidator(1000)],
        help_text='Лимит для каждой фоновой команды (от 1 до 1000).',
    )
    max_attempts = models.PositiveSmallIntegerField(
        'Попыток доставки', default=5,
        validators=[MinValueValidator(1), MaxValueValidator(10)],
        help_text='Число попыток при временной ошибке MAX (от 1 до 10).',
    )
    updated_at = models.DateTimeField('Последнее изменение', auto_now=True)

    class Meta:
        verbose_name = 'Настройки уведомлений MAX'
        verbose_name_plural = 'Настройки уведомлений MAX'
        constraints = [
            models.CheckConstraint(
                condition=models.Q(pk=1), name='max_notification_settings_singleton',
            ),
        ]

    def clean(self):
        super().clean()
        try:
            self.site_url = normalize_site_origin(self.site_url)
        except ValueError as exc:
            raise ValidationError({'site_url': str(exc)}) from exc

    def save(self, *args, **kwargs):
        if self.pk != 1:
            raise ValueError('Допускается только одна запись настроек MAX.')
        return super().save(*args, **kwargs)

    @classmethod
    def current(cls):
        # The migration seeds the record. If it was removed outside Admin,
        # fail closed: recreate with both notification channels disabled.
        instance, _ = cls.objects.get_or_create(pk=1)
        return instance

    def __str__(self):
        return 'Настройки уведомлений MAX'
