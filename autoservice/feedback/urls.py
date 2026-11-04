from django.urls import path

from .views import FeedbackStatisticsView, max_feedback_webhook


urlpatterns = [
    path('max/webhook/', max_feedback_webhook, name='max-feedback-webhook'),
    path('statistics/', FeedbackStatisticsView.as_view(), name='feedback-statistics'),
]
