from django.urls import path

from integrations.views import OneCTestConnectionView


urlpatterns = [
    path("test/", OneCTestConnectionView.as_view(), name="onec-test"),
]
