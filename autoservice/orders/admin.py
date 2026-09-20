from django.contrib import admin

from orders.models import (
    AppointmentSettings,
    Order,
    OrderStatus,
    ScheduleBlock,
    WeekdaySchedule,
    WorkStatus,
    WorkType,
)


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


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'customer', 'car', 'work_type', 'status', 'work_status', 'appointment_at', 'price')
    list_filter = ('status', 'work_status', 'work_type')
    search_fields = ('order_number', 'customer__phone', 'car__plate_number')
