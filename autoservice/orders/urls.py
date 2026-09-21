from django.urls import include, path
from rest_framework import routers

from .views import (
    AppointmentAvailabilityView,
    AppointmentScheduleView,
    OrderStatusViewSet,
    OrderViewSet,
    WorkStatusViewSet,
    WorkTypeViewSet,
)

router = routers.DefaultRouter()

router.register(
    r'order-status',
    OrderStatusViewSet,
    basename='orderStatus',
)

router.register(
    r'work-status',
    WorkStatusViewSet,
    basename='workStatus',
)

router.register(
    r'work-type',
    WorkTypeViewSet,
    basename='workType',
)

router.register(r'', OrderViewSet, basename='orders')

urlpatterns = [
    path('schedule/', AppointmentScheduleView.as_view(), name='appointmentSchedule'),
    path('availability/', AppointmentAvailabilityView.as_view(), name='appointmentAvailability'),
    path('', include(router.urls)),
]
