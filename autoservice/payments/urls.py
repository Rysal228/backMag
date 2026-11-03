from django.urls import path

from .views import OrderPaymentPreviewView, OrderPaymentStartView, PaymentCapabilitiesView

urlpatterns = [
    path("capabilities/", PaymentCapabilitiesView.as_view(), name="payment-capabilities"),
    path("orders/<uuid:order_id>/preview/", OrderPaymentPreviewView.as_view(), name="payment-preview"),
    path("orders/<uuid:order_id>/start/", OrderPaymentStartView.as_view(), name="payment-start"),
]
