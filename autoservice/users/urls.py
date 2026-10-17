from django.urls import path, include
from django.conf import settings
from .views import *
from .onec_profile_views import OneCProfileView
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
        (OneCProfileView if settings.ONEC_PROFILE_GATEWAY_ENABLED else ProfileCustomUserView).as_view(),
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
