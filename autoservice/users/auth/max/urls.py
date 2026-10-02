from django.urls import path

from .views import (
    MaxAuthView,
    MaxCodeRequestView,
    MaxCodeVerifyView,
)


urlpatterns = [
    path(
        '',
        MaxAuthView.as_view(),
        name='auth-max',
    ),
    path(
        'code/request/',
        MaxCodeRequestView.as_view(),
        name='auth-max-code-request',
    ),
    path(
        'code/verify/',
        MaxCodeVerifyView.as_view(),
        name='auth-max-code-verify',
    ),
]
