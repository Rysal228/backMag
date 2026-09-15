from django.urls import path, include
from .views import *
from rest_framework import routers

router = routers.DefaultRouter()

router.register(
    r'',
    CustomUserViewSet,
    basename='users',
)

router.register(
    r'profile',
    ProfileCustomUserViewSet,
    basename='profile',
)


urlpatterns = [
    path(
        '',
        include(router.urls),
    ),

    path(
        'auth/',
        include('users.auth.urls'),
    ),
]