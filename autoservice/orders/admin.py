"""Order business data is managed in 1C; Django Admin configures only UI filters."""
from django.contrib import admin
from orders.models import OrderFilterPermission


@admin.register(OrderFilterPermission)
class OrderFilterPermissionAdmin(admin.ModelAdmin):
    list_display = ("role", "filter_key", "enabled")
    list_filter = ("role", "filter_key", "enabled")
    list_editable = ("enabled",)
    search_fields = ("role", "filter_key")
    ordering = ("role", "filter_key")
