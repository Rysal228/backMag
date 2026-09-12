from django.urls import path, include
from rest_framework import routers

from .views import CarViewSet, CarBrandViewSet, CarModelViewSet

router = routers.DefaultRouter()

router.register(r'', CarViewSet, basename='cars')

router.register(
    r'brands',
    CarBrandViewSet,
    basename='brands',
)

router.register(
    r'models',
    CarModelViewSet,
    basename='models',
)

urlpatterns = [
    path('', include(router.urls)),
]