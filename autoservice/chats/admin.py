"""Only chat messages/rooms live in Django; orders are native 1C UUIDs."""
from django.contrib import admin
from chats.models import ChatMessage, ChatRoom


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    can_delete = False
    readonly_fields = ("id", "sender_id", "text", "created_at")
    fields = ("id", "sender_id", "text", "created_at")


@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ("order_id", "type", "mechanic_id", "created_at")
    list_filter = ("type", "created_at")
    search_fields = ("order_id", "mechanic_id")
    readonly_fields = ("id", "created_at")
    inlines = (ChatMessageInline,)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ("room", "sender_id", "created_at")
    list_filter = ("created_at",)
    search_fields = ("text", "sender_id", "room__order_id")
    readonly_fields = ("id", "room", "sender_id", "text", "created_at")

    def has_add_permission(self, request):
        return False
