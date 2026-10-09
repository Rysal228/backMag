from django.urls import re_path

from chats.consumers import OrderChatConsumer

websocket_urlpatterns = [
    re_path(r'^ws/chats/(?P<room_id>[0-9a-fA-F-]+)/$', OrderChatConsumer.as_asgi()),
]
