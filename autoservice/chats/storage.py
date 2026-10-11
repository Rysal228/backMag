from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateChatAttachmentStorage(FileSystemStorage):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('location', settings.CHAT_ATTACHMENT_ROOT)
        # Deliberately not served by Django's public MEDIA_URL route.
        kwargs.setdefault('base_url', '/private-chat-attachments/')
        super().__init__(*args, **kwargs)
