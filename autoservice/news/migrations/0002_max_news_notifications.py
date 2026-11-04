from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [('news', '0001_initial')]

    operations = [
        migrations.CreateModel(
            name='NewsNotificationBatch',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=255)),
                ('excerpt', models.TextField(blank=True)),
                ('is_global', models.BooleanField(default=False)),
                ('roles', models.JSONField(default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('prepared_at', models.DateTimeField(blank=True, null=True)),
                ('news', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='max_publication', to='news.news')),
            ],
            options={'verbose_name': 'MAX-публикация новости', 'verbose_name_plural': 'MAX-публикации новостей', 'ordering': ('created_at', 'pk')},
        ),
        migrations.CreateModel(
            name='NewsNotificationDelivery',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('recipient_id', models.UUIDField()),
                ('state', models.CharField(choices=[('pending', 'В очереди'), ('sent', 'Отправлено'), ('skipped', 'Получатель недоступен'), ('failed', 'Не доставлено')], default='pending', max_length=12)),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('next_attempt_at', models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('sent_at', models.DateTimeField(blank=True, null=True)),
                ('publication', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='deliveries', to='news.newsnotificationbatch')),
            ],
            options={'verbose_name': 'MAX-уведомление о новости', 'verbose_name_plural': 'MAX-уведомления о новостях', 'ordering': ('created_at', 'pk')},
        ),
        migrations.AddConstraint(
            model_name='newsnotificationdelivery',
            constraint=models.UniqueConstraint(fields=('publication', 'recipient_id'), name='unique_news_max_delivery'),
        ),
    ]
