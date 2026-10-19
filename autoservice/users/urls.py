from django.urls import include, path

from .onec_profile_views import OneCProfileView
from .views import UserListView

urlpatterns = [
    path("profile/", OneCProfileView.as_view(), name="profile"),
    path("auth/", include("users.auth.urls")),
    path("", UserListView.as_view(), name="users-list"),
]
