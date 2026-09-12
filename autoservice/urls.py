from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),

    path('api/auth/', include('users.auth.urls')),

    path('api/v1/users/', include('users.urls')),
    path('api/v1/cars/', include('cars.urls')),
    path('api/v1/orders/', include('orders.urls')),
]