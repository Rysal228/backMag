from pathlib import Path

from rest_framework import serializers

from chats.models import ChatAttachment, ChatMessage, ChatRoom


MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024
ALLOWED_ATTACHMENT_TYPES = {
    '.jpg': ('image/jpeg',),
    '.jpeg': ('image/jpeg',),
    '.png': ('image/png',),
    '.webp': ('image/webp',),
    '.pdf': ('application/pdf',),
}


class ChatAttachmentSerializer(serializers.ModelSerializer):
    downloadUrl = serializers.SerializerMethodField()
    originalName = serializers.CharField(source='original_name', read_only=True)
    contentType = serializers.CharField(source='content_type', read_only=True)
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)

    class Meta:
        model = ChatAttachment
        fields = ('id', 'originalName', 'contentType', 'size', 'downloadUrl', 'createdAt')
        read_only_fields = fields

    def get_downloadUrl(self, obj):
        return f'/api/v1/chats/attachments/{obj.pk}/download/'


class ChatMessageSerializer(serializers.ModelSerializer):
    senderId = serializers.UUIDField(source='sender_id', read_only=True)
    senderName = serializers.SerializerMethodField()
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    attachments = ChatAttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = ChatMessage
        fields = ('id', 'senderId', 'senderName', 'text', 'createdAt', 'attachments')
        read_only_fields = fields

    def get_senderName(self, obj):
        return obj.sender.get_full_name() or obj.sender.phone


class ChatRoomSerializer(serializers.ModelSerializer):
    orderId = serializers.UUIDField(source='order_id', read_only=True)
    orderNumber = serializers.CharField(source='order.order_number', read_only=True)
    mechanicId = serializers.UUIDField(source='mechanic_id', read_only=True, allow_null=True)
    mechanicName = serializers.SerializerMethodField()
    typeLabel = serializers.CharField(source='get_type_display', read_only=True)
    createdAt = serializers.DateTimeField(source='created_at', read_only=True)
    lastMessage = serializers.SerializerMethodField()

    class Meta:
        model = ChatRoom
        fields = (
            'id', 'orderId', 'orderNumber', 'type', 'typeLabel',
            'mechanicId', 'mechanicName', 'createdAt', 'lastMessage',
        )
        read_only_fields = fields

    def get_mechanicName(self, obj):
        if not obj.mechanic_id:
            return None
        return obj.mechanic.get_full_name() or obj.mechanic.phone

    def get_lastMessage(self, obj):
        message = obj.messages.select_related('sender').prefetch_related('attachments').order_by('-created_at').first()
        if message is None:
            return None
        return ChatMessageSerializer(message).data


class ChatAttachmentUploadField(serializers.FileField):
    default_error_messages = {
        'too_large': 'Размер одного файла не должен превышать 10 МБ.',
        'unsupported_type': 'Разрешены только изображения JPEG, PNG, WebP и документы PDF.',
        'invalid_content': 'Содержимое файла не соответствует поддерживаемому формату.',
    }

    def to_internal_value(self, data):
        uploaded = super().to_internal_value(data)
        if uploaded.size > MAX_ATTACHMENT_SIZE:
            self.fail('too_large')

        extension = Path(uploaded.name).suffix.lower()
        if extension not in ALLOWED_ATTACHMENT_TYPES:
            self.fail('unsupported_type')

        header = uploaded.read(16)
        uploaded.seek(0)
        signatures = {
            '.jpg': header.startswith(b'\xff\xd8\xff'),
            '.jpeg': header.startswith(b'\xff\xd8\xff'),
            '.png': header.startswith(b'\x89PNG\r\n\x1a\n'),
            '.webp': header.startswith(b'RIFF') and header[8:12] == b'WEBP',
            '.pdf': header.startswith(b'%PDF-'),
        }
        if not signatures.get(extension, False):
            self.fail('invalid_content')

        uploaded.detected_chat_content_type = ALLOWED_ATTACHMENT_TYPES[extension][0]
        return uploaded


class SendChatMessageSerializer(serializers.Serializer):
    text = serializers.CharField(max_length=5000, allow_blank=True, required=False, trim_whitespace=True)
    files = serializers.ListField(
        child=ChatAttachmentUploadField(),
        required=False,
        allow_empty=False,
        max_length=5,
    )

    def validate(self, attrs):
        text = attrs.get('text', '').strip()
        files = attrs.get('files', [])
        if not text and not files:
            raise serializers.ValidationError('Добавьте текст сообщения или хотя бы один файл.')
        attrs['text'] = text
        return attrs
