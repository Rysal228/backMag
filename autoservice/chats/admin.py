from django.contrib import admin

from chats.models import ChatMessage, ChatRoom


class ChatMessageInline(admin.TabularInline):
    model = ChatMessage
    extra = 0
    can_delete = False
    readonly_fields = ('id', 'sender', 'text', 'created_at')
    fields = ('id', 'sender', 'text', 'created_at')


@admin.register(ChatRoom)
class ChatRoomAdmin(admin.ModelAdmin):
    list_display = ('order', 'type', 'mechanic', 'created_at')
    list_filter = ('type', 'created_at')
    search_fields = ('order__order_number', 'order__customer__phone', 'mechanic__phone')
    readonly_fields = ('id', 'created_at')
    inlines = (ChatMessageInline,)


@admin.register(ChatMessage)
class ChatMessageAdmin(admin.ModelAdmin):
    list_display = ('room', 'sender', 'created_at')
    list_filter = ('created_at',)
    search_fields = ('text', 'sender__phone', 'room__order__order_number')
    readonly_fields = ('id', 'room', 'sender', 'text', 'created_at')

    def has_add_permission(self, request):
        return False
