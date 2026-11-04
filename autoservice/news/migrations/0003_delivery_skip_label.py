from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('news', '0002_max_news_notifications')]

    operations = [
        migrations.AlterField(
            model_name='newsnotificationdelivery',
            name='state',
            field=models.CharField(
                choices=[
                    ('pending', 'В очереди'),
                    ('sent', 'Отправлено'),
                    ('skipped', 'Пропущено'),
                    ('failed', 'Не доставлено'),
                ],
                default='pending', max_length=12,
            ),
        ),
    ]
