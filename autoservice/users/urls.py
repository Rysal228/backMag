from django.urls import include, path

from users.onec_profile_views import OneCProfileView
from users.views import UserDetailView, UserListView

urlpatterns = [
    path('profile/', OneCProfileView.as_view(), name='profile'),
    path('auth/', include('users.auth.urls')),
    path('', UserListView.as_view(), name='users-list'),
    path('<uuid:user_id>/', UserDetailView.as_view(), name='users-detail'),
]
