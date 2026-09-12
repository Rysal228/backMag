from django.urls import path

from .views import MaxAuthView


urlpatterns = [
    path(
        '',
        MaxAuthView.as_view(),
        name='auth-max',
    ),
]