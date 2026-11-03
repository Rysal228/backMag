"""Read-only payment preparation and explicitly disabled payment creation."""
from decimal import Decimal, InvalidOperation
from uuid import UUID

from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from integrations.services.onec_orders import OneCOrdersClient
from users.models import UserRole


NOT_CONFIGURED = {
    "enabled": False,
    "provider": None,
    "methods": [],
    "code": "payments_not_configured",
}


def require_customer(request):
    if request.active_role != UserRole.USER:
        raise PermissionDenied("Онлайн-оплата доступна только владельцу заказа.")


def parse_order_id(order_id):
    try:
        return str(UUID(str(order_id)))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError({"orderId": "Некорректный идентификатор заказа."}) from exc


class PaymentCapabilitiesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # Status is deliberately constant: no real processor is connected.
        return Response(NOT_CONFIGURED)


class OrderPaymentPreviewView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, order_id):
        require_customer(request)
        order_id = parse_order_id(order_id)
        # 1C checks order visibility for actorId; never trust browser-provided owner/price.
        order = OneCOrdersClient().get(order_id, request.user.id, request.active_role)
        try:
            amount = Decimal(str(order["price"]))
        except (KeyError, ValueError, TypeError, InvalidOperation) as exc:
            raise ValidationError({"amount": "Не удалось определить стоимость заказа."}) from exc
        if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2:
            raise ValidationError({"amount": "Некорректная стоимость заказа."})
        payment_status = order.get("paymentStatus")
        return Response({
            "orderId": order_id,
            "amount": format(amount, ".2f"),
            "currency": "RUB",
            "paymentStatus": payment_status,
            "canPay": False,
            "reason": "payments_not_configured",
        })


class OrderPaymentStartView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, order_id):
        require_customer(request)
        parse_order_id(order_id)
        # Deliberately no provider call, DB write, or 1C status transition.
        return Response(
            {"code": "payments_not_configured", "message": "Онлайн-оплата ещё не подключена."},
            status=503,
        )
