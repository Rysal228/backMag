from django.urls import path

from .views import max_feedback_webhook


urlpatterns = [
    path('max/webhook/', max_feedback_webhook, name='max-feedback-webhook'),
]
