"""Expand and send new Django Admin news announcements to MAX."""
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from integrations.services.onec_notifications import OneCNewsRecipientsClient, OneCNotificationError
from news.services.max_notifications import news_url, prepare_news_deliveries, send_news_deliveries


class Command(BaseCommand):
    help = 'Создать очередь оповещений о новых новостях и отправить через MAX.'

    def add_arguments(self, parser):
        parser.add_argument('--prepare-only', action='store_true')
        parser.add_argument('--send-only', action='store_true')
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, *args, **options):
        if not settings.MAX_NEWS_NOTIFICATIONS_ENABLED:
            raise CommandError('Включите MAX_NEWS_NOTIFICATIONS_ENABLED=1 после настройки.')
        if options['prepare_only'] and options['send_only']:
            raise CommandError('Укажите только один из --prepare-only / --send-only.')
        if not 1 <= options['limit'] <= 1000:
            raise CommandError('--limit должен быть от 1 до 1000.')
        try:
            OneCNewsRecipientsClient()
            news_url(1)
        except (OneCNotificationError, ValueError, TypeError) as exc:
            raise CommandError('Проверьте служебный ключ 1С и HTTPS URL сайта.') from exc

        if not options['send_only']:
            try:
                result = prepare_news_deliveries()
            except Exception as exc:
                raise CommandError('Не удалось получить получателей новостей из 1С.') from exc
            self.stdout.write(f"Публикации: prepared={result['prepared']}, queued={result['queued']}")
        if not options['prepare_only']:
            try:
                result = send_news_deliveries(limit=options['limit'])
            except Exception as exc:
                raise CommandError('Не удалось проверить получателей новостей в 1С.') from exc
            self.stdout.write('MAX: ' + ', '.join(f'{k}={v}' for k, v in result.items()))
