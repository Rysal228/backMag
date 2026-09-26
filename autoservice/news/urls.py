from rest_framework import routers

from .views import NewsViewSet

router = routers.DefaultRouter()
router.register(r'', NewsViewSet, basename='news')

urlpatterns = router.urls
