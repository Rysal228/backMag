from django.contrib import admin
from django.http import HttpResponseRedirect
from django.urls import reverse

from .models import MaxNotificationSettings


@admin.register(MaxNotificationSettings)
class MaxNotificationSettingsAdmin(admin.ModelAdmin):
    """One editable settings page with no delete or additional records."""

    fieldsets = (
        ('Каналы уведомлений', {
            'fields': ('orders_enabled', 'news_enabled'),
            'description': 'Заказы: очередь приостанавливается. Новости: после включения отправляются только новые публикации.',
        }),
        ('Ссылки в сообщениях', {'fields': ('site_url',)}),
        ('Информация', {'fields': ('updated_at',)}),
    )
    readonly_fields = ('updated_at',)
    list_display = ('__str__', 'orders_enabled', 'news_enabled', 'updated_at')

    def has_add_permission(self, request):
        return super().has_add_permission(request) and not MaxNotificationSettings.objects.filter(pk=1).exists()

    def has_delete_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        if self.has_change_permission(request) and MaxNotificationSettings.objects.filter(pk=1).exists():
            return HttpResponseRedirect(reverse(
                'admin:notifications_maxnotificationsettings_change', args=(1,),
            ))
        return super().changelist_view(request, extra_context)
