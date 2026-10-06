from django.urls import include, path

from .views import (
    LoginView,
    RegisterView,
    RefreshTokenView,
    PasswordView,
    SwitchRoleView,
)

urlpatterns = [
    path('login/', LoginView.as_view()),
    path('register/', RegisterView.as_view()),
    path('switch-role/', SwitchRoleView.as_view()),
    path('password/', PasswordView.as_view()),
    path('max/', include('users.auth.max.urls')),
    path('token/refresh/', RefreshTokenView.as_view()),
]
