"""No network or database needed: payment endpoints must fail closed."""
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

from django.test import SimpleTestCase
from rest_framework.exceptions import PermissionDenied, ValidationError

from .views import PaymentCapabilitiesView, OrderPaymentPreviewView, OrderPaymentStartView


ORDER = UUID("21afe47c-5403-4805-9442-b1d10e84f97d")
CUSTOMER = UUID("8996ef81-9116-4d75-a3de-2fa8a5bc6b10")


def actor(role="user"):
    return SimpleNamespace(active_role=role, user=SimpleNamespace(id=CUSTOMER))


class PaymentFoundationTests(SimpleTestCase):
    def test_capabilities_always_disabled(self):
        data = PaymentCapabilitiesView().get(actor()).data
        self.assertFalse(data["enabled"])
        self.assertEqual(data["methods"], [])
        self.assertIsNone(data["provider"])

    @patch("payments.views.OneCOrdersClient")
    def test_preview_uses_authenticated_customer_and_1c_price(self, gateway):
        gateway.return_value.get.return_value = {
            "price": "1750.50", "paymentStatus": {"code": "unpaid", "name": "Не оплачено"},
        }
        response = OrderPaymentPreviewView().get(actor(), ORDER)
        self.assertEqual(response.data["amount"], "1750.50")
        self.assertFalse(response.data["canPay"])
        gateway.return_value.get.assert_called_once_with(str(ORDER), CUSTOMER, "user")

    @patch("payments.views.OneCOrdersClient")
    def test_preview_denies_mechanics_and_managers(self, gateway):
        for role in ("mechanic", "admin"):
            with self.subTest(role=role), self.assertRaises(PermissionDenied):
                OrderPaymentPreviewView().get(actor(role), ORDER)
        gateway.assert_not_called()

    @patch("payments.views.OneCOrdersClient")
    def test_preview_rejects_invalid_amount_and_uuid(self, gateway):
        for value in ("NaN", "-1", "invalid", "10.001"):
            gateway.return_value.get.return_value = {"price": value}
            with self.subTest(value=value), self.assertRaises(ValidationError):
                OrderPaymentPreviewView().get(actor(), ORDER)
        with self.assertRaises(ValidationError):
            OrderPaymentPreviewView().get(actor(), "not-an-order")

    @patch("payments.views.OneCOrdersClient")
    def test_start_never_contacts_gateway_or_creates_payment(self, gateway):
        response = OrderPaymentStartView().post(actor(), ORDER)
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["code"], "payments_not_configured")
        gateway.assert_not_called()
        with self.assertRaises(PermissionDenied):
            OrderPaymentStartView().post(actor("mechanic"), ORDER)
