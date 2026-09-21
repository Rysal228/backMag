from django.contrib import admin

from orders.models import (
    AppointmentSettings,
    BusySlot,
    Order,
    OrderStatus,
    ScheduleBlock,
    WeekdaySchedule,
    WorkStatus,
    WorkType,
)
from orders.services.appointment_availability import AppointmentAvailabilityService



@admin.register(WorkType)
class WorkTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(OrderStatus)
class OrderStatusAdmin(admin.ModelAdmin):
    list_display = ('name', 'appearance', 'is_initial', 'requires_payment')
    list_filter = ('appearance', 'is_initial', 'requires_payment')
    search_fields = ('name',)


@admin.register(WorkStatus)
class WorkStatusAdmin(admin.ModelAdmin):
    list_display = ('name', 'appearance')
    list_filter = ('appearance',)
    search_fields = ('name',)


@admin.register(AppointmentSettings)
class AppointmentSettingsAdmin(admin.ModelAdmin):
    list_display = ('appointment_duration', 'slot_interval')

    def has_add_permission(self, request):
        return not AppointmentSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WeekdaySchedule)
class WeekdayScheduleAdmin(admin.ModelAdmin):
    list_display = ('weekday', 'is_working', 'start_time', 'end_time')
    list_filter = ('is_working',)
    ordering = ('weekday',)


@admin.register(ScheduleBlock)
class ScheduleBlockAdmin(admin.ModelAdmin):
    list_display = ('date', 'start_time', 'end_time')
    list_filter = ('date',)
    ordering = ('date', 'start_time')


@admin.register(BusySlot)
class BusySlotAdmin(admin.ModelAdmin):
    list_display = ('date', 'start_time', 'end_time', 'order')
    list_filter = ('date',)
    search_fields = ('order__order_number',)
    ordering = ('date', 'start_time')


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'customer', 'car', 'work_type', 'status', 'work_status', 'appointment_at', 'price')
    list_filter = ('status', 'work_status', 'work_type')
    search_fields = ('order_number', 'customer__phone', 'car__plate_number')

    def save_model(self, request, obj, form, change):
        previous_appointment = None
        if change:
            previous_appointment = Order.objects.get(pk=obj.pk).appointment_at

        super().save_model(request, obj, form, change)

        if not change or previous_appointment != obj.appointment_at:
            AppointmentAvailabilityService.sync_order_busy_slot(obj)
