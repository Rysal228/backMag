from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from users.models import UserRole


class News(models.Model):
    class Meta:
        verbose_name = 'Новость'
        verbose_name_plural = 'Новости'
        ordering = ('-created_at',)

    title = models.CharField(
        verbose_name='Заголовок',
        max_length=255,
    )

    content = models.TextField(
        verbose_name='Текст',
        blank=True,
    )

    image = models.ImageField(
        verbose_name='Изображение',
        upload_to='news/',
        null=True,
        blank=True,
    )

    is_global = models.BooleanField(
        verbose_name='Для всех ролей',
        default=False,
    )

    created_at = models.DateTimeField(
        verbose_name='Дата создания',
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        verbose_name='Дата изменения',
        auto_now=True,
    )

    def clean(self):
        super().clean()

        if not self.content.strip() and not self.image:
            raise ValidationError({
                'content': 'Новость должна содержать текст или изображение.',
            })

    def __str__(self):
        return self.title


class NewsRole(models.Model):
    class Meta:
        verbose_name = 'Роль новости'
        verbose_name_plural = 'Роли новости'
        constraints = [
            models.UniqueConstraint(
                fields=('news', 'role'),
                name='unique_news_role',
            ),
        ]

    news = models.ForeignKey(
        News,
        on_delete=models.CASCADE,
        related_name='role_targets',
    )

    role = models.CharField(
        verbose_name='Роль',
        max_length=20,
        choices=UserRole.choices,
    )

    def __str__(self):
        return self.get_role_display()


class NewsNotificationBatch(models.Model):
    """One immutable publication event, recorded after Admin saves its roles."""

    news = models.OneToOneField(News, on_delete=models.CASCADE, related_name='max_publication')
    title = models.CharField(max_length=255)
    excerpt = models.TextField(blank=True)
    is_global = models.BooleanField(default=False)
    roles = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
    prepared_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'MAX-публикация новости'
        verbose_name_plural = 'MAX-публикации новостей'
        ordering = ('created_at', 'pk')


class NewsNotificationDelivery(models.Model):
    """Outgoing journal keyed by 1C UUID; MAX identifiers stay in 1C."""

    class State(models.TextChoices):
        PENDING = 'pending', 'В очереди'
        SENT = 'sent', 'Отправлено'
        SKIPPED = 'skipped', 'Пропущено'
        FAILED = 'failed', 'Не доставлено'

    publication = models.ForeignKey(
        NewsNotificationBatch, on_delete=models.CASCADE, related_name='deliveries',
    )
    recipient_id = models.UUIDField()
    state = models.CharField(max_length=12, choices=State.choices, default=State.PENDING)
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'MAX-уведомление о новости'
        verbose_name_plural = 'MAX-уведомления о новостях'
        ordering = ('created_at', 'pk')
        constraints = [
            models.UniqueConstraint(
                fields=('publication', 'recipient_id'), name='unique_news_max_delivery',
            ),
        ]
