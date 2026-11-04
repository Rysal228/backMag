"""Expand and send new Django Admin news announcements to MAX."""
from django.core.management.base import BaseCommand, CommandError

from integrations.services.onec_notifications import OneCNewsRecipientsClient, OneCNotificationError
from notifications.models import MaxNotificationSettings
from news.services.max_notifications import news_url, prepare_news_deliveries, send_news_deliveries


class Command(BaseCommand):
    help = 'Создать очередь оповещений о новых новостях и отправить через MAX.'

    def add_arguments(self, parser):
        parser.add_argument('--prepare-only', action='store_true')
        parser.add_argument('--send-only', action='store_true')
        parser.add_argument('--limit', type=int, default=None)

    def handle(self, *args, **options):
        if options['prepare_only'] and options['send_only']:
            raise CommandError('Укажите только один из --prepare-only / --send-only.')
        config = MaxNotificationSettings.current()
        limit = options['limit'] if options['limit'] is not None else config.send_limit
        if not 1 <= limit <= 1000:
            raise CommandError('--limit должен быть от 1 до 1000.')
        if not config.news_enabled:
            self.stdout.write('MAX: уведомления о новостях приостановлены в Django Admin.')
            return
        try:
            OneCNewsRecipientsClient()
            news_url(1, site_url=config.site_url)
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
                result = send_news_deliveries(
                    limit=limit, site_url=config.site_url, max_attempts=config.max_attempts,
                )
            except Exception as exc:
                raise CommandError('Не удалось проверить получателей новостей в 1С.') from exc
            self.stdout.write('MAX: ' + ', '.join(f'{k}={v}' for k, v in result.items()))
