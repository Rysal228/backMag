"""Cron worker for order evaluation requests; independent from status messages."""
from django.core.management.base import BaseCommand, CommandError

from feedback.services import observe_feedback_orders, send_feedback_invitations
from integrations.services.onec_notifications import OneCNotificationsClient, OneCNotificationError
from notifications.models import MaxNotificationSettings


class Command(BaseCommand):
    help = 'Найти новые закрытые/отменённые заказы и отправить запросы оценок в MAX.'

    def add_arguments(self, parser):
        parser.add_argument('--observe-only', action='store_true')
        parser.add_argument('--send-only', action='store_true')
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, *args, **options):
        if options['observe_only'] and options['send_only']:
            raise CommandError('Укажите только один из --observe-only / --send-only.')
        limit = options['limit']
        if not 1 <= limit <= 1000:
            raise CommandError('--limit должен быть от 1 до 1000.')
        if not MaxNotificationSettings.current().feedback_enabled:
            self.stdout.write('MAX: опросы клиентов выключены в Django Admin.')
            return
        try:
            OneCNotificationsClient()
        except OneCNotificationError as exc:
            raise CommandError('Проверьте ONEC_NOTIFICATIONS_SERVICE_KEY и адрес 1С.') from exc
        if not options['send_only']:
            try:
                result = observe_feedback_orders()
            except Exception as exc:
                raise CommandError('Не удалось получить статусы заказов из 1С.') from exc
            self.stdout.write(f"1С: baseline={result['baseline']}, queued={result['queued']}")
        if not options['observe_only']:
            try:
                result = send_feedback_invitations(limit=limit)
            except Exception as exc:
                raise CommandError('Не удалось проверить получателей в 1С.') from exc
            self.stdout.write('MAX: ' + ', '.join(f'{k}={v}' for k, v in result.items()))
