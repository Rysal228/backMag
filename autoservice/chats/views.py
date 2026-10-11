from pathlib import Path

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import permissions, serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from chats.models import ChatAttachment, ChatMessage, ChatRoom
from chats.permissions import can_access_order_chats, can_access_room
from chats.serializers import ChatMessageSerializer, ChatRoomSerializer, SendChatMessageSerializer
from orders.models import Order
from users.models import UserRole


class OrderChatRoomsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, order_id):
        order = get_object_or_404(
            Order.objects.prefetch_related('mechanics'),
            pk=order_id,
        )
        if not can_access_order_chats(order, request):
            raise PermissionDenied('Нет доступа к чатам этого заказа.')

        rooms = []
        role = request.active_role

        if role in (UserRole.USER, UserRole.ADMIN):
            room, _ = ChatRoom.objects.get_or_create(
                order=order,
                type=ChatRoom.Type.CUSTOMER_MANAGER,
                defaults={'mechanic': None},
            )
            rooms.append(room)

        if role == UserRole.ADMIN:
            for mechanic in order.mechanics.all():
                room, _ = ChatRoom.objects.get_or_create(
                    order=order,
                    type=ChatRoom.Type.MANAGER_MECHANIC,
                    mechanic=mechanic,
                )
                rooms.append(room)
        elif role == UserRole.MECHANIC:
            room, _ = ChatRoom.objects.get_or_create(
                order=order,
                type=ChatRoom.Type.MANAGER_MECHANIC,
                mechanic=request.user,
            )
            rooms.append(room)

        return Response(ChatRoomSerializer(rooms, many=True).data)


class ChatMessagesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, room_id):
        room = get_object_or_404(
            ChatRoom.objects.select_related('order', 'mechanic'),
            pk=room_id,
        )
        if not can_access_room(room, request):
            raise PermissionDenied('Нет доступа к этому чату.')

        queryset = room.messages.select_related('sender').prefetch_related('attachments').order_by('-created_at', '-id')
        before = request.query_params.get('before')
        if before:
            before_value = serializers.DateTimeField().run_validation(before)
            queryset = queryset.filter(created_at__lt=before_value)

        try:
            page_size = int(request.query_params.get('limit', 50))
        except (TypeError, ValueError):
            raise serializers.ValidationError({'limit': 'Параметр limit должен быть числом.'})
        if page_size < 1 or page_size > 100:
            raise serializers.ValidationError({'limit': 'Параметр limit должен быть от 1 до 100.'})
        messages = list(queryset[:page_size])
        messages.reverse()
        return Response({
            'results': ChatMessageSerializer(messages, many=True).data,
            'hasMore': len(messages) == page_size,
        })

    def post(self, request, room_id):
        room = get_object_or_404(
            ChatRoom.objects.select_related('order', 'mechanic'),
            pk=room_id,
        )
        if not can_access_room(room, request):
            raise PermissionDenied('Нет доступа к этому чату.')

        serializer = SendChatMessageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data
        message = ChatMessage.objects.create(
            room=room,
            sender=request.user,
            text=validated.get('text', ''),
        )

        for uploaded in validated.get('files', []):
            attachment = ChatAttachment.objects.create(
                message=message,
                file=uploaded,
                original_name=Path(uploaded.name.replace(chr(92), '/')).name[:255],
                content_type=uploaded.detected_chat_content_type,
                size=uploaded.size,
            )

        message_data = ChatMessageSerializer(message).data
        message_data['roomId'] = str(room.pk)
        async_to_sync(get_channel_layer().group_send)(
            f'chat_{room.pk.hex}',
            {'type': 'chat.message', 'message': message_data},
        )
        return Response(
            message_data,
            status=status.HTTP_201_CREATED,
        )


class ChatAttachmentDownloadView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, attachment_id):
        attachment = get_object_or_404(
            ChatAttachment.objects.select_related('message__room__order', 'message__room__mechanic'),
            pk=attachment_id,
        )
        if not can_access_room(attachment.message.room, request):
            raise PermissionDenied('Нет доступа к этому вложению.')

        try:
            file_handle = attachment.file.open('rb')
        except (FileNotFoundError, OSError):
            raise Http404('Файл не найден.')

        safe_name = Path(attachment.original_name).name.replace('"', '')
        response = FileResponse(
            file_handle,
            as_attachment=True,
            filename=safe_name,
            content_type='application/octet-stream',
        )
        response['X-Content-Type-Options'] = 'nosniff'
        response['Cache-Control'] = 'private, no-store'
        return response
