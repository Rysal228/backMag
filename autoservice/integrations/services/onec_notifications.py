"""Read-only service API for the notification worker; no application actor."""
import os
import re
from urllib.parse import urlsplit
from uuid import UUID

import requests
from django.conf import settings

from integrations.services.onec_users import DEFAULT_BASE_URL


class OneCNotificationError(RuntimeError):
    """Safe diagnostic: never include credentials or upstream response bodies."""


def canonical_uuid(value):
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        raise OneCNotificationError("1С вернула некорректный UUID уведомления.") from None


class OneCNotificationsClient:
    def __init__(self):
        self.key = getattr(settings, "ONEC_NOTIFICATIONS_SERVICE_KEY", "")
        if not isinstance(self.key, str) or not re.fullmatch(r"[A-Za-z0-9_-]{32,128}", self.key):
            raise OneCNotificationError(
                "Укажите ONEC_NOTIFICATIONS_SERVICE_KEY: 32–128 символов A–Z, a–z, 0–9, _ или -."
            )
        base = os.environ.get("ONEC_BASE_URL", DEFAULT_BASE_URL).rstrip("/")
        parsed = urlsplit(base)
        if (
            not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path
            or (parsed.scheme != "https" and base != DEFAULT_BASE_URL)
        ):
            raise OneCNotificationError("Недопустимый адрес служебного API уведомлений 1С.")
        path = os.environ.get("ONEC_ORDERS_PATH", "/ServiceCar/hs/api").strip("/")
        if not path or any(x in path for x in ("?", "#", "..", "//", "\\")):
            raise OneCNotificationError("Недопустимый путь служебного API уведомлений 1С.")
        self.base = f"{base}/{path}/notifications/orders"

    def _get(self, suffix="", *, allow_missing=False):
        try:
            response = requests.get(
                self.base + suffix,
                headers={"Accept": "application/json", "X-ServiceCar-Notifications-Key": self.key},
                timeout=30 if not suffix else 10,
                allow_redirects=False,
            )
        except requests.RequestException:
            raise OneCNotificationError("Не удалось обратиться к API уведомлений 1С.") from None
        if allow_missing and response.status_code == 404:
            return None
        if response.status_code in (401, 403):
            raise OneCNotificationError("1С отклонила служебный ключ уведомлений.")
        if response.status_code != 200:
            raise OneCNotificationError("API уведомлений 1С вернул ошибку HTTP.")
        try:
            return response.json()
        except ValueError:
            raise OneCNotificationError("API уведомлений 1С вернул некорректный JSON.") from None

    @staticmethod
    def _status(value):
        if not isinstance(value, dict) or set(value) != {"code", "name"}:
            raise OneCNotificationError("Некорректная структура статуса уведомления 1С.")
        if not all(isinstance(value[x], str) for x in ("code", "name")):
            raise OneCNotificationError("Некорректное значение статуса уведомления 1С.")
        return value

    def list_orders(self):
        records = self._get()
        if not isinstance(records, list):
            raise OneCNotificationError("1С вернула некорректную ленту уведомлений.")
        result, seen = [], set()
        for item in records:
            if not isinstance(item, dict):
                raise OneCNotificationError("1С вернула некорректную запись уведомления.")
            row = dict(item)
            row["id"] = canonical_uuid(row.get("id"))
            row["car"] = canonical_uuid(row.get("car"))
            row["ownerId"] = canonical_uuid(row["ownerId"]) if row.get("ownerId") else None
            if row["id"] in seen:
                raise OneCNotificationError("В ленте уведомлений повторяется заказ.")
            seen.add(row["id"])
            for field in ("orderNumber", "carName"):
                if not isinstance(row.get(field), str):
                    raise OneCNotificationError("Некорректные реквизиты уведомления 1С.")
            row["status"] = self._status(row.get("status"))
            row["workStatus"] = self._status(row.get("workStatus"))
            result.append(row)
        # Validate the entire feed before the worker changes any snapshots.
        return result

    def recipient(self, order_id):
        expected = canonical_uuid(order_id)
        row = self._get(f"/{expected}/recipient", allow_missing=True)
        if row is None:
            return None
        if not isinstance(row, dict) or type(row.get("eligible")) is not bool:
            raise OneCNotificationError("Некорректный получатель уведомления 1С.")
        result = dict(row)
        result["id"] = canonical_uuid(row.get("id"))
        result["car"] = canonical_uuid(row.get("car"))
        result["ownerId"] = canonical_uuid(row["ownerId"]) if row.get("ownerId") else None
        if result["id"] != expected:
            raise OneCNotificationError("1С вернула получателя другого заказа.")
        max_id = row.get("messengerUserId")
        if not isinstance(max_id, str):
            raise OneCNotificationError("Некорректная MAX-привязка получателя 1С.")
        if row["eligible"] and (
            not result["ownerId"] or not re.fullmatch(r"[0-9]{1,20}", max_id)
        ):
            raise OneCNotificationError("Некорректная MAX-привязка получателя 1С.")
        return result
