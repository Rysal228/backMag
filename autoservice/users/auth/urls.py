from django.urls import include, path

from .views import (
    LoginView,
    RegisterView,
    RefreshTokenView, PasswordView,
)

from ..views import LogoutView


urlpatterns = [
    path(
        'login/',
        LoginView.as_view(),
        name='auth-login',
    ),

    path(
        'register/',
        RegisterView.as_view(),
        name='auth-register',
    ),

    path(
        'password/',
        PasswordView.as_view(),
        name='auth-password',
    ),

    path(
        'max/',
        include('users.auth.max.urls'),
    ),

    path(
        'token/refresh/',
        RefreshTokenView.as_view(),
        name='auth-token-refresh',
    ),

    path(
        'logout/',
        LogoutView.as_view(),
        name='auth-logout',
    ),
]