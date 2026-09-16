from django.urls import path, include
from .views import *
from rest_framework import routers

router = routers.DefaultRouter()

router.register(
    r'',
    CustomUserViewSet,
    basename='users',
)

urlpatterns = [
    path(
        'profile/',
        ProfileCustomUserView.as_view(),
        name='profile',
    ),
    path(
        '',
        include(router.urls),
    ),
    path(
        'auth/',
        include('users.auth.urls'),
    ),
]
