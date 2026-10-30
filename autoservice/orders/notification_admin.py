from django.contrib import admin

from orders.models import OrderNotificationDelivery, OrderNotificationSnapshot


class ImmutableNotificationAdmin(admin.ModelAdmin):
    """Inspection only: never fabricate messages or delivery states in Admin."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OrderNotificationSnapshot)
class OrderNotificationSnapshotAdmin(ImmutableNotificationAdmin):
    list_display = ("order_id", "order_code", "work_code", "revision", "observed_at")
    search_fields = ("=order_id",)
    readonly_fields = ("order_id", "car_id", "owner_id", "order_code",
                       "work_code", "revision", "observed_at")


@admin.register(OrderNotificationDelivery)
class OrderNotificationDeliveryAdmin(ImmutableNotificationAdmin):
    list_display = ("order_number", "state", "attempts", "created_at", "sent_at")
    list_filter = ("state",)
    search_fields = ("=order_id", "order_number")
    readonly_fields = (
        "order_id", "car_id", "owner_id", "revision", "order_number",
        "car_name", "order_code", "work_code", "order_changed",
        "work_changed", "state", "attempts", "created_at", "sent_at",
    )
