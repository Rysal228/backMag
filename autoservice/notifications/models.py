"""Operator-controlled notification settings. Bot and 1C secrets stay in env."""
from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


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
        help_text='После включения уведомления отправляются только о новых публикациях.',
    )
    news_enabled_since = models.DateTimeField(
        'Последнее включение новостной рассылки', null=True, blank=True, editable=False,
    )
    feedback_enabled = models.BooleanField(
        'Приглашения оценить обслуживание', default=False,
        help_text='Только новые закрытия и отмены заказов после включения. Старые заказы не рассылаются.',
    )
    feedback_enabled_since = models.DateTimeField(
        'Последнее включение опросов', null=True, blank=True, editable=False,
    )
    feedback_delay_minutes = models.PositiveIntegerField(
        'Отправить приглашение через, минут', default=30,
        validators=[MinValueValidator(0), MaxValueValidator(10080)],
        help_text='Одинаковая задержка для закрытия и отмены заказа (0–10080 минут).',
    )
    feedback_low_max = models.PositiveSmallIntegerField(
        'Низкая оценка: до (включительно)', default=3,
        validators=[MinValueValidator(1), MaxValueValidator(4)],
    )
    feedback_high_min = models.PositiveSmallIntegerField(
        'Высокая оценка: от (включительно)', default=4,
        validators=[MinValueValidator(2), MaxValueValidator(5)],
        help_text='Оценки между этими границами считаются нейтральными.',
    )
    site_url = models.URLField(
        'Адрес сайта для ссылок', max_length=255, blank=True,
        help_text='Например: https://www.cherser-car.site. Если пусто, ссылки не добавляются.',
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
        if self.feedback_low_max is not None and self.feedback_high_min is not None:
            if self.feedback_low_max >= self.feedback_high_min:
                raise ValidationError({'feedback_high_min': 'Высокая оценка должна начинаться выше диапазона низких.'})

    def save(self, *args, **kwargs):
        if self.pk != 1:
            raise ValueError('Допускается только одна запись настроек MAX.')
        update_fields = kwargs.get('update_fields')
        if self._state.adding:
            self.news_enabled_since = timezone.now() if self.news_enabled else None
            self.feedback_enabled_since = timezone.now() if self.feedback_enabled else None
        else:
            previous = type(self).objects.filter(pk=self.pk).values(
                'news_enabled', 'feedback_enabled',
            ).first()
            for enabled_field, since_field in (
                ('news_enabled', 'news_enabled_since'),
                ('feedback_enabled', 'feedback_enabled_since'),
            ):
                if update_fields is not None and enabled_field not in update_fields:
                    continue
                if previous is not None and previous[enabled_field] != getattr(self, enabled_field):
                    setattr(self, since_field, timezone.now() if getattr(self, enabled_field) else None)
                    if update_fields is not None:
                        update_fields = set(update_fields) | {since_field}
            if update_fields is not None:
                kwargs['update_fields'] = update_fields
        return super().save(*args, **kwargs)

    @classmethod
    def current(cls):
        # The migration seeds the record. If it was removed outside Admin,
        # fail closed: recreate with both notification channels disabled.
        instance, _ = cls.objects.get_or_create(pk=1)
        return instance

    def __str__(self):
        return 'Настройки уведомлений MAX'
