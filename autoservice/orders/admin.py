from django.contrib import admin

from orders.models import Order, OrderStatus, WorkStatus, WorkType


@admin.register(WorkType)
class WorkTypeAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(OrderStatus)
class OrderStatusAdmin(admin.ModelAdmin):
    list_display = ('name', 'appearance', 'is_initial')
    list_filter = ('appearance', 'is_initial')
    search_fields = ('name',)


@admin.register(WorkStatus)
class WorkStatusAdmin(admin.ModelAdmin):
    list_display = ('name', 'appearance')
    list_filter = ('appearance',)
    search_fields = ('name',)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('order_number', 'customer', 'car', 'work_type', 'status', 'work_status', 'appointment_at', 'price')
    list_filter = ('status', 'work_status', 'work_type')
    search_fields = ('order_number', 'customer__phone', 'car__plate_number')
