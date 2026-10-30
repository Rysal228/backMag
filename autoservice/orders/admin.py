"""Order business data is managed in 1C; Django Admin configures only UI filters."""
from django.contrib import admin, messages
from django.db import transaction
from orders.models import OrderFilterPermission, StatisticsPeriodOption


@admin.register(OrderFilterPermission)
class OrderFilterPermissionAdmin(admin.ModelAdmin):
    list_display = ("role", "filter_key", "enabled")
    list_filter = ("role", "filter_key", "enabled")
    list_editable = ("enabled",)
    search_fields = ("role", "filter_key")
    ordering = ("role", "filter_key")


@admin.register(StatisticsPeriodOption)
class StatisticsPeriodOptionAdmin(admin.ModelAdmin):
    list_display = ("days", "enabled", "is_default")
    list_display_links = ("days",)
    list_editable = ("enabled",)
    ordering = ("days",)
    readonly_fields = ("is_default",)
    fields = ("days", "enabled", "is_default")
    actions = ("make_default",)

    @admin.action(description="Сделать выбранный период периодом по умолчанию")
    def make_default(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(
                request, "Выберите ровно один период.", level=messages.ERROR,
            )
            return

        period = queryset.get()
        if not period.enabled:
            self.message_user(
                request, "Сначала включите выбранный период.", level=messages.ERROR,
            )
            return

        with transaction.atomic():
            StatisticsPeriodOption.objects.filter(is_default=True).update(is_default=False)
            StatisticsPeriodOption.objects.filter(pk=period.pk).update(is_default=True)
        self.message_user(
            request, f"Период {period.days} дн. выбран по умолчанию.",
            level=messages.SUCCESS,
        )

# Register read-only MAX notification journal in Django Admin.
from . import notification_admin  # noqa: E402,F401
