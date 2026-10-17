from django.urls import path, include
from .views import CustomUserViewSet
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
        OneCProfileView.as_view(),
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
