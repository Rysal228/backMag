from django.urls import include, path

from .views import (
    LoginView,
    RegisterView,
    RefreshTokenView, PasswordView,
)

urlpatterns = [
    path('login/', LoginView.as_view()),
    path('register/', RegisterView.as_view()),
    path('password/', PasswordView.as_view()),
    path('max/', include('users.auth.max.urls')),
    path('token/refresh/', RefreshTokenView.as_view()),
]