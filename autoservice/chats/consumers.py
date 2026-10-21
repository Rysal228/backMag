from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.utils import timezone

from rest_framework_simplejwt.tokens import AccessToken
from users.authentication import validate_native_claims

from integrations.services.onec_users import OneCUsersClient

from chats.models import ChatMessage, ChatRoom
from chats.permissions import can_access_room_for


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
        if not isinstance(content, dict):
            await self._send_error('invalid_event', 'Событие должно быть JSON-объектом.')
            return

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

        user, role, expires_at, method, messenger, max_phone = result
        room = await self._get_accessible_room(user, role)
        if room is None:
            await self._send_error('chat_access_denied', 'Нет доступа к этому чату.')
            await self.close(code=4403)
            return

        self.user = user
        self.active_role = role
        self.token_expires_at = expires_at
        self.auth_method = method
        self.messenger_id = messenger
        self.max_verified_phone = max_phone
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
            token = AccessToken(raw_token)
            user, role = validate_native_claims(token)
            return (
                user, role, int(token["exp"]), token["auth_method"],
                token.get("messenger_user_id", ""), token.get("max_verified_phone", ""),
            )
        except Exception:
            return None

    @database_sync_to_async
    def _get_accessible_room(self, user, role):
        room = (
            ChatRoom.objects
            .filter(pk=self.scope['url_route']['kwargs']['room_id'])
            .first()
        )
        if room is None or not can_access_room_for(room, user, role):
            return None
        return room

    @database_sync_to_async
    def _still_authorized(self):
        try:
            profile = OneCUsersClient().get_user_by_onec_id(self.user.pk)
        except Exception:
            return False
        if (
            profile.get('isActive') is not True
            or self.active_role not in profile.get('roles', [])
            or profile.get('onecId') != str(self.user.pk)
        ):
            return False
        if self.auth_method == 'max' and (
            self.messenger_id != profile.get('messengerUserId')
            or self.max_verified_phone != profile.get('phone')
        ):
            return False
        room = (
            ChatRoom.objects
            .filter(pk=self.room.pk)
            .first()
        )
        return bool(room and can_access_room_for(room, self.user, self.active_role))

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
            'attachments': [],
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
