import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('orders', '0027_remove_status_appearance'),
    ]

    operations = [
        migrations.CreateModel(
            name='ChatRoom',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('type', models.CharField(choices=[('customer_manager', 'Пользователь — менеджер'), ('manager_mechanic', 'Менеджер — механик')], max_length=32, verbose_name='Тип чата')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('mechanic', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='mechanic_chat_rooms', to=settings.AUTH_USER_MODEL, verbose_name='Механик')),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='chat_rooms', to='orders.order', verbose_name='Заказ')),
            ],
            options={
                'verbose_name': 'Чат заказа',
                'verbose_name_plural': 'Чаты заказов',
                'ordering': ('created_at',),
            },
        ),
        migrations.CreateModel(
            name='ChatMessage',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('text', models.TextField(max_length=5000, verbose_name='Сообщение')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('room', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='messages', to='chats.chatroom', verbose_name='Чат')),
                ('sender', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='chat_messages', to=settings.AUTH_USER_MODEL, verbose_name='Отправитель')),
            ],
            options={
                'verbose_name': 'Сообщение чата',
                'verbose_name_plural': 'Сообщения чатов',
                'ordering': ('created_at', 'id'),
            },
        ),
        migrations.AddConstraint(
            model_name='chatroom',
            constraint=models.CheckConstraint(
                condition=(Q(('type', 'customer_manager'), ('mechanic__isnull', True)) | Q(('type', 'manager_mechanic'), ('mechanic__isnull', False))),
                name='chat_room_type_mechanic_consistency',
            ),
        ),
        migrations.AddConstraint(
            model_name='chatroom',
            constraint=models.UniqueConstraint(condition=Q(('type', 'customer_manager')), fields=('order',), name='unique_customer_manager_chat_per_order'),
        ),
        migrations.AddConstraint(
            model_name='chatroom',
            constraint=models.UniqueConstraint(condition=Q(('type', 'manager_mechanic')), fields=('order', 'mechanic'), name='unique_manager_mechanic_chat_per_order'),
        ),
        migrations.AddIndex(
            model_name='chatmessage',
            index=models.Index(fields=['room', 'created_at'], name='chat_msg_room_created_idx'),
        ),
    ]
