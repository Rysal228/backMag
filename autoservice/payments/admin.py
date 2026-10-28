"""Read-only journal; operations may only be written by verified provider logic."""
from django.contrib import admin
from .models import PaymentAttempt, PaymentEvent


class PaymentReadOnlyAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaymentAttempt)
class PaymentAttemptAdmin(PaymentReadOnlyAdmin):
    list_display = ("order_id", "provider", "amount", "currency", "status", "created_at")
    list_filter = ("provider", "status", "currency")
    search_fields = ("=order_id", "=customer_id", "provider_payment_id")


@admin.register(PaymentEvent)
class PaymentEventAdmin(PaymentReadOnlyAdmin):
    list_display = ("provider", "provider_event_id", "received_at", "verified_at")
    list_filter = ("provider",)
    search_fields = ("provider_event_id",)
