from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone
from rest_framework_simplejwt.authentication import JWTAuthentication

from chats.models import ChatMessage, ChatRoom
from chats.permissions import can_access_room_for
from users.models import CustomUser


class OrderChatConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.user = None
        self.active_role = None
        self.room = None
        self.group_name = None
        self.token_expires_at = None
        await self.accept()

    async def disconnect(self, close_code):
        if self.group_name:
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content, **kwargs):
        if self.user is None:
            await self._authenticate(content)
            return

        if self.token_expires_at is None or timezone.now().timestamp() >= self.token_expires_at:
            await self._send_error('token_expired', 'Срок действия токена истёк. Переподключитесь.')
            await self.close(code=4401)
            return

        if not await self._still_authorized():
            await self._send_error('chat_access_revoked', 'Доступ к этому чату больше не разрешён.')
            await self.close(code=4403)
            return

        if content.get('type') != 'send_message':
            await self.send_json({
                'type': 'error',
                'code': 'unsupported_event',
                'message': 'Неизвестный тип события.',
            })
            return

        text = content.get('text')
        if not isinstance(text, str):
            await self._send_error('invalid_message', 'Текст сообщения должен быть строкой.')
            return

        text = text.strip()
        if not text:
            await self._send_error('empty_message', 'Сообщение не может быть пустым.')
            return
        if len(text) > 5000:
            await self._send_error('message_too_long', 'Максимальная длина сообщения — 5000 символов.')
            return

        message = await self._create_message(text)
        await self.channel_layer.group_send(
            self.group_name,
            {
                'type': 'chat.message',
                'message': message,
            },
        )

    async def _authenticate(self, content):
        if content.get('type') != 'authenticate' or not isinstance(content.get('token'), str):
            await self._send_error('authentication_required', 'Сначала необходимо авторизоваться.')
            await self.close(code=4401)
            return

        result = await self._authenticate_token(content['token'])
        if result is None:
            await self._send_error('invalid_token', 'Токен недействителен или срок его действия истёк.')
            await self.close(code=4401)
            return

        user, role, expires_at = result
        room = await self._get_accessible_room(user.pk, role)
        if room is None:
            await self._send_error('chat_access_denied', 'Нет доступа к этому чату.')
            await self.close(code=4403)
            return

        self.user = user
        self.active_role = role
        self.token_expires_at = expires_at
        self.room = room
        self.group_name = f'chat_{room.pk.hex}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.send_json({
            'type': 'authenticated',
            'roomId': str(room.pk),
        })

    @database_sync_to_async
    def _authenticate_token(self, raw_token):
        try:
            token = JWTAuthentication().get_validated_token(raw_token)
            user = JWTAuthentication().get_user(token)
        except Exception:
            return None

        role = token.get('active_role')
        if not role or not user.has_role(role):
            return None
        return user, role, int(token['exp'])

    @database_sync_to_async
    def _get_accessible_room(self, user_id, role):
        room = (
            ChatRoom.objects
            .select_related('order', 'mechanic')
            .filter(pk=self.scope['url_route']['kwargs']['room_id'])
            .first()
        )
        user = CustomUser.objects.filter(pk=user_id).first()
        if room is None or user is None or not can_access_room_for(room, user, role):
            return None
        return room

    @database_sync_to_async
    def _still_authorized(self):
        user = CustomUser.objects.filter(pk=self.user.pk).first()
        room = (
            ChatRoom.objects
            .select_related('order', 'mechanic')
            .filter(pk=self.room.pk)
            .first()
        )
        return bool(
            user
            and room
            and user.has_role(self.active_role)
            and can_access_room_for(room, user, self.active_role)
        )

    @database_sync_to_async
    def _create_message(self, text):
        message = ChatMessage.objects.create(
            room_id=self.room.pk,
            sender_id=self.user.pk,
            text=text,
        )
        return {
            'id': str(message.pk),
            'roomId': str(self.room.pk),
            'senderId': str(self.user.pk),
            'senderName': self.user.get_full_name() or self.user.phone,
            'text': message.text,
            'createdAt': message.created_at.isoformat(),
        }

    async def chat_message(self, event):
        if self.token_expires_at is None or timezone.now().timestamp() >= self.token_expires_at:
            await self.close(code=4401)
            return
        await self.send_json({
            'type': 'message',
            'message': event['message'],
        })

    async def _send_error(self, code, message):
        await self.send_json({
            'type': 'error',
            'code': code,
            'message': message,
        })
