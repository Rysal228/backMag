"""Poll authoritative 1C and deliver due MAX notifications (scheduled CLI)."""
from uuid import UUID

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from orders.services.max_notifications import (
    poll_order_statuses, public_order_url, send_pending_notifications,
)


class Command(BaseCommand):
    help = "Сверить статусы заказов 1С и отправить уведомления клиентам в MAX."

    def add_arguments(self, parser):
        parser.add_argument("--observe-only", action="store_true")
        parser.add_argument("--send-only", action="store_true")
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        if not settings.MAX_ORDER_NOTIFICATIONS_ENABLED:
            raise CommandError(
                "Включите MAX_ORDER_NOTIFICATIONS_ENABLED=1 после настройки и проверки."
            )
        if options["observe_only"] and options["send_only"]:
            raise CommandError("Укажите только один из --observe-only / --send-only.")
        if not 1 <= options["limit"] <= 1000:
            raise CommandError("--limit должен быть от 1 до 1000.")
        try:
            UUID(str(settings.MAX_ORDER_NOTIFICATIONS_MANAGER_ID))
            # Validate URL before writing queue rows or contacting MAX.
            public_order_url("00000000-0000-0000-0000-000000000000")
        except (ValueError, TypeError) as exc:
            raise CommandError(
                "Укажите UUID менеджера в MAX_ORDER_NOTIFICATIONS_MANAGER_ID "
                "и корректный HTTPS URL (если задан)."
            ) from exc

        if not options["send_only"]:
            try:
                counts = poll_order_statuses()
            except Exception as exc:
                raise CommandError("Не удалось получить актуальные статусы из 1С.") from exc
            self.stdout.write(
                f"1С: создано снимков {counts['baseline']}, "
                f"в очереди {counts['queued']}, без владельца {counts['unmapped']}"
            )

        if not options["observe_only"]:
            results = send_pending_notifications(limit=options["limit"])
            self.stdout.write(
                "MAX: " + ", ".join(f"{key}={value}" for key, value in results.items())
            )
