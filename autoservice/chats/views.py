from django.shortcuts import get_object_or_404
from rest_framework import permissions, serializers, status
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from chats.models import ChatMessage, ChatRoom
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

        queryset = room.messages.select_related('sender').order_by('-created_at', '-id')
        before = request.query_params.get('before')
        if before:
            queryset = queryset.filter(created_at__lt=before)

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
        message = ChatMessage.objects.create(
            room=room,
            sender=request.user,
            text=serializer.validated_data['text'],
        )
        return Response(
            ChatMessageSerializer(message).data,
            status=status.HTTP_201_CREATED,
        )
