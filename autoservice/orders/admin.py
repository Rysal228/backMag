from django.contrib import admin

from orders.models import Order, WorkType, OrderStatus



admin.site.register(WorkType)
admin.site.register(OrderStatus)
admin.site.register(Order)