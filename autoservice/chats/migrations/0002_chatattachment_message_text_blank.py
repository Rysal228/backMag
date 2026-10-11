import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('chats', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='chatmessage',
            name='text',
            field=models.TextField(blank=True, max_length=5000, verbose_name='Сообщение'),
        ),
        migrations.CreateModel(
            name='ChatAttachment',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('file', models.FileField(upload_to='chat_attachments/%Y/%m/')),
                ('original_name', models.CharField(max_length=255, verbose_name='Имя файла')),
                ('content_type', models.CharField(max_length=100, verbose_name='Тип содержимого')),
                ('size', models.PositiveBigIntegerField(verbose_name='Размер, байт')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('message', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='attachments', to='chats.chatmessage', verbose_name='Сообщение')),
            ],
            options={
                'verbose_name': 'Вложение сообщения',
                'verbose_name_plural': 'Вложения сообщений',
                'ordering': ('created_at',),
            },
        ),
    ]
