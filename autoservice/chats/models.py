import uuid

from django.db import models
from django.db.models import Q

from chats.storage import PrivateChatAttachmentStorage


class ChatRoom(models.Model):
    class Type(models.TextChoices):
        CUSTOMER_MANAGER = 'customer_manager', 'Пользователь — менеджер'
        MANAGER_MECHANIC = 'manager_mechanic', 'Менеджер — механик'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    # Native UUID of 1C Document.ЗаказыНаОбслуживание (no local Order ORM).
    order_id = models.UUIDField(db_index=True, verbose_name='Заказ 1С')
    type = models.CharField(
        max_length=32,
        choices=Type.choices,
        verbose_name='Тип чата',
    )
    mechanic_id = models.UUIDField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Чат заказа'
        verbose_name_plural = 'Чаты заказов'
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(type='customer_manager', mechanic_id__isnull=True)
                    | Q(type='manager_mechanic', mechanic_id__isnull=False)
                ),
                name='chat_room_type_mechanic_consistency',
            ),
            models.UniqueConstraint(
                fields=('order_id',),
                condition=Q(type='customer_manager'),
                name='unique_customer_manager_chat_per_order',
            ),
            models.UniqueConstraint(
                fields=('order_id', 'mechanic_id'),
                condition=Q(type='manager_mechanic'),
                name='unique_manager_mechanic_chat_per_order',
            ),
        ]
        ordering = ('created_at',)

    def __str__(self):
        return f'Чат {self.get_type_display()} — заказ {self.order_id}'


class ChatMessage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name='messages',
        verbose_name='Чат',
    )
    sender_id = models.UUIDField(db_index=True)
    text = models.TextField(max_length=5000, blank=True, verbose_name='Сообщение')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Сообщение чата'
        verbose_name_plural = 'Сообщения чатов'
        ordering = ('created_at', 'id')
        indexes = [
            models.Index(fields=('room', 'created_at'), name='chat_msg_room_created_idx'),
        ]

    def __str__(self):
        return f'{self.sender_id}: {self.text[:50]}'


class ChatAttachment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    message = models.ForeignKey(
        ChatMessage,
        on_delete=models.CASCADE,
        related_name='attachments',
        verbose_name='Сообщение',
    )
    file = models.FileField(
        upload_to='chat_attachments/%Y/%m/',
        storage=PrivateChatAttachmentStorage(),
    )
    original_name = models.CharField(max_length=255, verbose_name='Имя файла')
    content_type = models.CharField(max_length=100, verbose_name='Тип содержимого')
    size = models.PositiveBigIntegerField(verbose_name='Размер, байт')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Вложение сообщения'
        verbose_name_plural = 'Вложения сообщений'
        ordering = ('created_at',)

    def __str__(self):
        return self.original_name
