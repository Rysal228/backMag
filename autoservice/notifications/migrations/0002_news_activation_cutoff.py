from django.db import migrations, models
from django.utils import timezone


def initialize_news_cutoff(apps, schema_editor):
    settings = apps.get_model('notifications', 'MaxNotificationSettings')
    # Previously queued publications must not be sent just because the admin
    # switched to the new behavior. Only new publications after this point.
    settings.objects.using(schema_editor.connection.alias).filter(
        news_enabled=True,
    ).update(news_enabled_since=timezone.now())


class Migration(migrations.Migration):
    dependencies = [('notifications', '0001_initial')]

    operations = [
        migrations.AddField(
            model_name='maxnotificationsettings',
            name='news_enabled_since',
            field=models.DateTimeField(
                blank=True, editable=False, null=True,
                verbose_name='Последнее включение новостной рассылки',
            ),
        ),
        migrations.AlterField(
            model_name='maxnotificationsettings',
            name='news_enabled',
            field=models.BooleanField(
                default=False,
                help_text='После включения уведомления отправляются только о новых публикациях.',
                verbose_name='Уведомления о новых публикациях',
            ),
        ),
        migrations.RemoveField(model_name='maxnotificationsettings', name='send_limit'),
        migrations.RemoveField(model_name='maxnotificationsettings', name='max_attempts'),
        migrations.RunPython(initialize_news_cutoff, migrations.RunPython.noop),
    ]
