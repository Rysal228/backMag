from django.urls import path

from chats.views import ChatAttachmentDownloadView, ChatMessagesView, OrderChatRoomsView

urlpatterns = [
    path('orders/<uuid:order_id>/', OrderChatRoomsView.as_view(), name='order-chat-rooms'),
    path('rooms/<uuid:room_id>/messages/', ChatMessagesView.as_view(), name='chat-messages'),
    path('attachments/<uuid:attachment_id>/download/', ChatAttachmentDownloadView.as_view(), name='chat-attachment-download'),
]
