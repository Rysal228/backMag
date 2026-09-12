from django.urls import path, include
from rest_framework import routers

from .views import OrderViewSet, WorkTypeViewSet, OrderStatusViewSet

router = routers.DefaultRouter()

router.register(r'', OrderViewSet, basename='orders')

router.register(
    r'work-type',
    WorkTypeViewSet,
    basename='workType',
)

router.register(
    r'order-status',
    OrderStatusViewSet,
    basename='orderStatus',
)

urlpatterns = [
    path('', include(router.urls)),
]