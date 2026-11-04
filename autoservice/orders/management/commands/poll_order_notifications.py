"""Poll authoritative 1C and deliver due MAX notifications (scheduled CLI)."""
from django.core.management.base import BaseCommand, CommandError

from integrations.services.onec_notifications import OneCNotificationsClient, OneCNotificationError
from notifications.models import MaxNotificationSettings

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
        if options["observe_only"] and options["send_only"]:
            raise CommandError("Укажите только один из --observe-only / --send-only.")
        config = MaxNotificationSettings.current()
        limit = options['limit']
        if not 1 <= limit <= 1000:
            raise CommandError("--limit должен быть от 1 до 1000.")
        if not config.orders_enabled:
            self.stdout.write('MAX: уведомления о заказах приостановлены в Django Admin.')
            return
        try:
            OneCNotificationsClient()
            # Validate URL before writing queue rows or contacting MAX.
            public_order_url("00000000-0000-0000-0000-000000000000", site_url=config.site_url)
        except (ValueError, TypeError, OneCNotificationError) as exc:
            raise CommandError(
                "Проверьте ONEC_NOTIFICATIONS_SERVICE_KEY, адрес 1С "
                "и корректный HTTPS URL сайта (если задан)."
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
            results = send_pending_notifications(
                limit=limit, site_url=config.site_url,
            )
            self.stdout.write(
                "MAX: " + ", ".join(f"{key}={value}" for key, value in results.items())
            )
