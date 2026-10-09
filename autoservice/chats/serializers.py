from rest_framework import serializers

from chats.models import ChatMessage, ChatRoom


class ChatMessageSerializer(serializers.ModelSerializer):
    senderId = serializers.UUIDField(source='sender_id', read_only=True)
    senderName = serializers.SerializerMethodField()
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)

    class Meta:
        model = ChatMessage
        fields = ('id', 'senderId', 'senderName', 'text', 'createdAt')
        read_only_fields = fields

    def get_senderName(self, obj):
        return obj.sender.get_full_name() or obj.sender.phone


class ChatRoomSerializer(serializers.ModelSerializer):
    orderId = serializers.UUIDField(source='order_id', read_only=True)
    orderNumber = serializers.CharField(source='order.order_number', read_only=True)
    mechanicId = serializers.UUIDField(source='mechanic_id', read_only=True, allow_null=True)
    mechanicName = serializers.SerializerMethodField()
    typeLabel = serializers.CharField(source='get_type_display', read_only=True)
    lastMessage = serializers.SerializerMethodField()

    class Meta:
        model = ChatRoom
        fields = (
            'id', 'orderId', 'orderNumber', 'type', 'typeLabel',
            'mechanicId', 'mechanicName', 'created_at', 'lastMessage',
        )
        read_only_fields = fields

    def get_mechanicName(self, obj):
        if not obj.mechanic_id:
            return None
        return obj.mechanic.get_full_name() or obj.mechanic.phone

    def get_lastMessage(self, obj):
        message = obj.messages.select_related('sender').order_by('-created_at').first()
        if message is None:
            return None
        return ChatMessageSerializer(message).data


class SendChatMessageSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=5000, allow_blank=False, trim_whitespace=True)

    def validate_text(self, value):
        if not value:
            raise serializers.ValidationError('Сообщение не может быть пустым.')
        return value
