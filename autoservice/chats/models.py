import uuid

from django.db import models
from django.db.models import Q

from orders.models import Order
from users.models import CustomUser


class ChatRoom(models.Model):
    class Type(models.TextChoices):
        CUSTOMER_MANAGER = 'customer_manager', 'Пользователь — менеджер'
        MANAGER_MECHANIC = 'manager_mechanic', 'Менеджер — механик'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    order = models.ForeignKey(
        Order,
        on_delete=models.CASCADE,
        related_name='chat_rooms',
        verbose_name='Заказ',
    )
    type = models.CharField(
        max_length=32,
        choices=Type.choices,
        verbose_name='Тип чата',
    )
    mechanic = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='mechanic_chat_rooms',
        verbose_name='Механик',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Чат заказа'
        verbose_name_plural = 'Чаты заказов'
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(type='customer_manager', mechanic__isnull=True)
                    | Q(type='manager_mechanic', mechanic__isnull=False)
                ),
                name='chat_room_type_mechanic_consistency',
            ),
            models.UniqueConstraint(
                fields=('order',),
                condition=Q(type='customer_manager'),
                name='unique_customer_manager_chat_per_order',
            ),
            models.UniqueConstraint(
                fields=('order', 'mechanic'),
                condition=Q(type='manager_mechanic'),
                name='unique_manager_mechanic_chat_per_order',
            ),
        ]
        ordering = ('created_at',)

    def __str__(self):
        return f'Чат {self.get_type_display()} — заказ №{self.order.order_number}'


class ChatMessage(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    room = models.ForeignKey(
        ChatRoom,
        on_delete=models.CASCADE,
        related_name='messages',
        verbose_name='Чат',
    )
    sender = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name='chat_messages',
        verbose_name='Отправитель',
    )
    text = models.TextField(max_length=5000, verbose_name='Сообщение')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Сообщение чата'
        verbose_name_plural = 'Сообщения чатов'
        ordering = ('created_at', 'id')
        indexes = [
            models.Index(fields=('room', 'created_at'), name='chat_msg_room_created_idx'),
        ]

    def __str__(self):
        return f'{self.sender}: {self.text[:50]}'
