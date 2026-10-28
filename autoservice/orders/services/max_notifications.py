"""MAX status notifications from 1C, including edits made inside 1C.

The polling worker stores only a last-observed state and a durable outbound
journal. Orders, statuses, and ownership remain authoritative in 1C.
"""
import logging
from datetime import timedelta
from urllib.parse import urlsplit
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from integrations.services.onec_cars import OneCCarsClient
from integrations.services.onec_orders import OneCOrdersClient
from integrations.services.onec_users import OneCUsersClient
from orders.models import OrderNotificationDelivery, OrderNotificationSnapshot
from users.auth.max.client import MaxBotClient

logger = logging.getLogger(__name__)
MAX_ATTEMPTS = 5

# 1C catalog names remain the authoritative Russian display labels.
# We intentionally do not report payment status here: it can currently be
# manually edited and is not evidence of a provider-confirmed transaction.


def safe_label(value, limit=120):
    return " ".join(str(value or "").split())[:limit]


def status_details(order):
    status = order.get("status") or {}
    work = order.get("workStatus") or {}
    return (
        safe_label(status.get("code"), 80),
        safe_label(work.get("code"), 80),
        safe_label(status.get("name")),
        safe_label(work.get("name")),
    )


def public_order_url(order_id):
    base = settings.MAX_ORDER_NOTIFICATIONS_PUBLIC_URL
    if not base:
        return ""
    parsed = urlsplit(base)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Public order URL must be an absolute HTTPS URL")
    return f"{base}/appointments/{order_id}"


def build_message(delivery):
    changes = []
    if delivery.order_changed:
        changes.append(f"Статус заказа: {safe_label(delivery.order_label) or delivery.order_code}")
    if delivery.work_changed:
        changes.append(f"Статус работ: {safe_label(delivery.work_label) or delivery.work_code}")
    message = (
        f"🚘 ServiceCar · Заказ №{safe_label(delivery.order_number, 100)}\n"
        f"{safe_label(delivery.car_name, 180)}\n\n"
        + "\n".join(changes)
    )
    url = public_order_url(delivery.order_id)
    if url:
        message += f"\n\nПодробнее: {url}"
    return message


def poll_order_statuses():
    """Observe all orders as a real configured 1C manager.

    Initial scan only creates baselines, never spams historical orders.
    One combined delivery is created when either order/work status changed.
    """
    manager_id = str(UUID(str(settings.MAX_ORDER_NOTIFICATIONS_MANAGER_ID)))
    orders = OneCOrdersClient().list_orders(manager_id, "admin")
    cars = OneCCarsClient().list_cars()
    owners = {str(UUID(str(c["id"]))): str(UUID(str(c["ownerId"]))) for c in cars}

    totals = {"baseline": 0, "queued": 0, "unmapped": 0}
    for order in orders:
        order_id = str(UUID(str(order["id"])))
        car_id = str(UUID(str(order["car"])))
        owner_id = owners.get(car_id)
        if not owner_id:
            # Fail closed: never guess the customer from a phone or car name.
            totals["unmapped"] += 1
            continue

        order_code, work_code, order_label, work_label = status_details(order)
        if not order_code:
            continue

        with transaction.atomic():
            state, created = OrderNotificationSnapshot.objects.get_or_create(
                order_id=order_id,
                defaults={
                    "car_id": car_id, "owner_id": owner_id,
                    "order_code": order_code, "work_code": work_code,
                },
            )
            if created:
                totals["baseline"] += 1
                continue

            state = OrderNotificationSnapshot.objects.select_for_update().get(pk=order_id)
            order_changed = state.order_code != order_code
            work_changed = state.work_code != work_code
            owner_changed = str(state.owner_id) != owner_id or str(state.car_id) != car_id

            if owner_changed:
                # Do not route a pending transition to a newly changed owner.
                # The next status transition can be delivered to the new owner.
                state.owner_id = owner_id
                state.car_id = car_id

            if order_changed or work_changed:
                state.revision += 1
                if not owner_changed:
                    OrderNotificationDelivery.objects.create(
                        order_id=order_id, car_id=car_id, owner_id=owner_id,
                        revision=state.revision,
                        order_number=safe_label(order.get("orderNumber"), 100),
                        car_name=safe_label(order.get("carName"), 180),
                        order_code=order_code, work_code=work_code,
                        order_label=order_label, work_label=work_label,
                        order_changed=order_changed, work_changed=work_changed,
                    )
                    totals["queued"] += 1

            state.order_code = order_code
            state.work_code = work_code
            state.save()

    return totals


def send_pending_notifications(limit=100):
    """Send queued messages with row locks and bounded exponential retry.

    A timeout after a successful remote delivery may still duplicate a message:
    the MAX endpoint does not provide an exactly-once guarantee here.
    """
    if not 1 <= limit <= 1000:
        raise ValueError("Invalid send limit")
    now = timezone.now()
    ids = list(
        OrderNotificationDelivery.objects.filter(
            state=OrderNotificationDelivery.State.PENDING,
            next_attempt_at__lte=now,
        ).order_by("created_at", "id").values_list("id", flat=True)[:limit * 3]
    )
    counts = {"sent": 0, "skipped": 0, "retry": 0, "failed": 0}
    processed_owners = set()

    for identifier in ids:
        if sum(counts.values()) >= limit:
            break
        with transaction.atomic():
            item = (
                OrderNotificationDelivery.objects.select_for_update(skip_locked=True)
                .filter(
                    pk=identifier, state=OrderNotificationDelivery.State.PENDING,
                    next_attempt_at__lte=timezone.now(),
                ).first()
            )
            if item is None:
                continue
            # MAX limits messages per conversation. Send at most one message
            # per customer per worker invocation; the rest wait for next poll.
            if item.owner_id in processed_owners:
                continue
            processed_owners.add(item.owner_id)
            try:
                # Verify current native ownership before routing any message.
                car = OneCCarsClient().get(str(item.car_id))
                if str(UUID(str(car["ownerId"]))) != str(item.owner_id):
                    item.state = OrderNotificationDelivery.State.SKIPPED
                    counts["skipped"] += 1
                else:
                    user = OneCUsersClient().get_user_by_onec_id(str(item.owner_id))
                    max_id = user.get("messengerUserId")
                    if (
                        user.get("isActive") is not True
                        or not isinstance(max_id, str)
                        or not max_id.isascii()
                        or not max_id.isdigit()
                        or not 1 <= len(max_id) <= 20
                    ):
                        item.state = OrderNotificationDelivery.State.SKIPPED
                        counts["skipped"] += 1
                    else:
                        MaxBotClient().send_message_to_user(
                            user_id=max_id, text=build_message(item),
                        )
                        item.state = OrderNotificationDelivery.State.SENT
                        item.sent_at = timezone.now()
                        counts["sent"] += 1
            except Exception:
                # No secrets, provider response bodies, phones or MAX IDs in logs.
                logger.exception("MAX order status delivery failed for queue row %s", identifier)
                item.attempts += 1
                if item.attempts >= MAX_ATTEMPTS:
                    item.state = OrderNotificationDelivery.State.FAILED
                    counts["failed"] += 1
                else:
                    item.next_attempt_at = timezone.now() + timedelta(
                        seconds=min(3600, 60 * (2 ** (item.attempts - 1)))
                    )
                    counts["retry"] += 1
            item.save()
    return counts
