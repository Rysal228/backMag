from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ('users', '0003_alter_customuser_username'),
    ]

    operations = [
        migrations.CreateModel(
            name='News',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'title',
                    models.CharField(
                        max_length=255,
                        verbose_name='Заголовок',
                    ),
                ),
                (
                    'content',
                    models.TextField(
                        blank=True,
                        verbose_name='Текст',
                    ),
                ),
                (
                    'image',
                    models.ImageField(
                        blank=True,
                        null=True,
                        upload_to='news/',
                        verbose_name='Изображение',
                    ),
                ),
                (
                    'is_global',
                    models.BooleanField(
                        default=False,
                        verbose_name='Для всех ролей',
                    ),
                ),
                (
                    'created_at',
                    models.DateTimeField(
                        auto_now_add=True,
                        verbose_name='Дата создания',
                    ),
                ),
                (
                    'updated_at',
                    models.DateTimeField(
                        auto_now=True,
                        verbose_name='Дата изменения',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Новость',
                'verbose_name_plural': 'Новости',
                'ordering': ('-created_at',),
            },
        ),
        migrations.CreateModel(
            name='NewsRole',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'role',
                    models.CharField(
                        choices=[
                            ('user', 'Пользователь'),
                            ('mechanic', 'Механик'),
                            ('admin', 'Администратор'),
                        ],
                        max_length=20,
                        verbose_name='Роль',
                    ),
                ),
                (
                    'news',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='role_targets',
                        to='news.news',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Роль новости',
                'verbose_name_plural': 'Роли новости',
            },
        ),
        migrations.AddConstraint(
            model_name='newsrole',
            constraint=models.UniqueConstraint(
                fields=('news', 'role'),
                name='unique_news_role',
            ),
        ),
    ]
