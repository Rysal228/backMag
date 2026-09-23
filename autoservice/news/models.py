from django.core.exceptions import ValidationError
from django.db import models

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
