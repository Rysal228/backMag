from django.urls import include, path
from rest_framework import routers

from .views import CarBrandViewSet, CarModelViewSet, CarViewSet

router = routers.DefaultRouter()

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

router.register(
    r'',
    CarViewSet,
    basename='cars',
)

urlpatterns = [
    path('', include(router.urls)),
]
