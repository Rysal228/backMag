from unittest.mock import patch
from uuid import UUID

from django.contrib import admin
from django.core.management import call_command
from django.db import transaction
from django.test import TestCase, SimpleTestCase, override_settings
from django.utils import timezone

from integrations.services.onec_notifications import OneCNewsRecipientsClient, OneCNotificationError
from news.admin import NewsAdmin, NewsAdminForm
from news.models import News, NewsRole, NewsNotificationBatch, NewsNotificationDelivery
from notifications.models import MaxNotificationSettings
from news.services.max_notifications import (
    can_read_news, news_url, prepare_news_deliveries, send_news_deliveries,
)


OWNER = 'aaaaaaaa-aaaa-4aaa-aaaa-aaaaaaaaaaaa'
MECHANIC = 'bbbbbbbb-bbbb-4bbb-bbbb-bbbbbbbbbbbb'
MANAGER = 'cccccccc-cccc-4ccc-cccc-cccccccccccc'


def recipient(max_id, *roles):
    return {'messengerUserId': max_id, 'roles': frozenset(roles)}


def feed():
    return {
        OWNER: recipient('12345', 'user'),
        MECHANIC: recipient('45678', 'mechanic'),
        MANAGER: recipient('78901', 'admin', 'user'),
    }


@override_settings(
    ONEC_NOTIFICATIONS_SERVICE_KEY='test_' + 'a' * 48,
)
class NewsMaxDeliveryTests(TestCase):
    def setUp(self):
        MaxNotificationSettings.objects.update_or_create(
            pk=1, defaults={
                'news_enabled': True,
                'site_url': 'https://www.cherser-car.site',
            },
        )

    def publish(self, *, title='Объявление', content='Приходите в субботу',
                is_global=False, roles=('mechanic',)):
        form = NewsAdminForm(data={
            'title': title, 'content': content,
            'is_global': 'on' if is_global else '', 'roles': list(roles),
        })
        self.assertTrue(form.is_valid(), form.errors)
        with transaction.atomic():
            news = form.save(commit=False)
            news.save()
            NewsAdmin(News, admin.site).save_related(None, form, [], False)
        return news

    def test_admin_publication_waits_for_roles_and_edits_do_not_repeat(self):
        news = self.publish()
        self.assertEqual(list(NewsRole.objects.filter(news=news).values_list('role', flat=True)),
                         ['mechanic'])
        batch = NewsNotificationBatch.objects.get(news=news)
        self.assertEqual(batch.roles, ['mechanic'])
        self.assertEqual(batch.title, 'Объявление')
        form = NewsAdminForm(data={
            'title': 'Исправленный заголовок', 'content': 'Новый текст',
            'roles': ['user'], 'is_global': '',
        }, instance=news)
        self.assertTrue(form.is_valid(), form.errors)
        with transaction.atomic():
            form.save(commit=False).save()
            NewsAdmin(News, admin.site).save_related(None, form, [], True)
        self.assertEqual(NewsNotificationBatch.objects.count(), 1)
        batch.refresh_from_db()
        self.assertEqual(batch.title, 'Объявление')

    @patch('news.services.max_notifications.OneCNewsRecipientsClient')
    def test_role_filter_and_exactly_once_preparation(self, gateway):
        news = self.publish()
        gateway.return_value.list_recipients.return_value = feed()
        self.assertEqual(prepare_news_deliveries(), {'prepared': 1, 'queued': 2})
        self.assertEqual(prepare_news_deliveries(), {'prepared': 0, 'queued': 0})
        self.assertEqual(
            set(NewsNotificationDelivery.objects.values_list('recipient_id', flat=True)),
            {UUID(MECHANIC), UUID(MANAGER)},
        )
        self.assertEqual(NewsNotificationBatch.objects.get(news=news).deliveries.count(), 2)
        gateway.return_value.list_recipients.assert_called_once()

    @patch('news.services.max_notifications.MaxBotClient')
    @patch('news.services.max_notifications.OneCNewsRecipientsClient')
    def test_send_uses_current_onec_max_id_not_postgres(self, gateway, bot):
        self.publish(is_global=True)
        gateway.return_value.list_recipients.return_value = feed()
        prepare_news_deliveries()
        self.assertEqual(send_news_deliveries()['sent'], 3)
        self.assertEqual(send_news_deliveries()['sent'], 0)
        self.assertEqual(bot.return_value.send_message_to_user.call_count, 3)
        texts = [call.kwargs['text'] for call in bot.return_value.send_message_to_user.call_args_list]
        self.assertTrue(all('https://www.cherser-car.site/main?news=' in text for text in texts))
        self.assertNotIn('12345', '\n'.join(texts))

    @patch('news.services.max_notifications.MaxBotClient')
    @patch('news.services.max_notifications.OneCNewsRecipientsClient')
    def test_revoked_binding_and_changed_roles_are_skipped(self, gateway, bot):
        news = self.publish(roles=('user',))
        gateway.return_value.list_recipients.return_value = feed()
        prepare_news_deliveries()
        # Manager and mechanic can see user news too, but a publication that is
        # later restricted by Admin must not go to the original broader audience.
        NewsRole.objects.filter(news=news).delete()
        NewsRole.objects.create(news=news, role='admin')
        updated = {MANAGER: feed()[MANAGER], OWNER: feed()[OWNER]}
        gateway.return_value.list_recipients.return_value = updated
        self.assertEqual(send_news_deliveries(), {
            'sent': 1, 'skipped': 2, 'retry': 0, 'failed': 0,
        })
        self.assertEqual(bot.return_value.send_message_to_user.call_count, 1)
        self.assertEqual(bot.return_value.send_message_to_user.call_args.kwargs['user_id'], '78901')

    @patch('news.services.max_notifications.MaxBotClient')
    @patch('news.services.max_notifications.OneCNewsRecipientsClient')
    def test_failed_delivery_retries_without_duplicate_queue_row(self, gateway, bot):
        self.publish(roles=('admin',))
        gateway.return_value.list_recipients.return_value = feed()
        prepare_news_deliveries()
        bot.return_value.send_message_to_user.side_effect = RuntimeError('provider error')
        before = timezone.now()
        self.assertEqual(send_news_deliveries()['retry'], 1)
        row = NewsNotificationDelivery.objects.get()
        self.assertEqual(row.attempts, 1)
        self.assertGreater(row.next_attempt_at, before)
        self.assertEqual(send_news_deliveries()['retry'], 0)
        self.assertEqual(NewsNotificationDelivery.objects.count(), 1)

    @patch('news.services.max_notifications.OneCNewsRecipientsClient')
    def test_invalid_service_feed_does_not_prepare_publication(self, gateway):
        self.publish()
        gateway.return_value.list_recipients.side_effect = OneCNotificationError('unavailable')
        with self.assertRaises(OneCNotificationError):
            prepare_news_deliveries()
        self.assertIsNone(NewsNotificationBatch.objects.get().prepared_at)
        self.assertFalse(NewsNotificationDelivery.objects.exists())

    @patch('news.services.max_notifications.OneCNewsRecipientsClient')
    def test_global_publication_with_no_recipients_is_not_rebroadcast(self, gateway):
        self.publish(is_global=True)
        gateway.return_value.list_recipients.return_value = {}
        self.assertEqual(prepare_news_deliveries(), {'prepared': 1, 'queued': 0})
        self.assertEqual(prepare_news_deliveries(), {'prepared': 0, 'queued': 0})

    @patch('news.management.commands.poll_news_notifications.OneCNewsRecipientsClient')
    def test_paused_feature_does_not_queue_publications_or_contact_1c(self, gateway):
        config = MaxNotificationSettings.current()
        config.news_enabled = False
        config.save()
        self.publish()
        self.assertEqual(NewsNotificationBatch.objects.count(), 0)
        call_command('poll_news_notifications')
        gateway.assert_not_called()

    @patch('news.services.max_notifications.MaxBotClient')
    @patch('news.services.max_notifications.OneCNewsRecipientsClient')
    @patch('news.management.commands.poll_news_notifications.OneCNewsRecipientsClient')
    def test_paused_publication_is_never_sent_after_resuming(self, command_client, service_client, bot):
        config = MaxNotificationSettings.current()
        config.news_enabled = False
        config.save()
        self.publish(roles=('admin',))
        call_command('poll_news_notifications')
        self.assertFalse(NewsNotificationBatch.objects.exists())
        bot.assert_not_called()
        config.news_enabled = True
        config.save()
        service_client.return_value.list_recipients.return_value = feed()
        call_command('poll_news_notifications')
        self.assertFalse(NewsNotificationDelivery.objects.exists())
        self.publish(title='После включения', roles=('admin',))
        call_command('poll_news_notifications')
        bot.return_value.send_message_to_user.assert_called_once()
        self.assertEqual(NewsNotificationDelivery.objects.count(), 1)

    @patch('news.services.max_notifications.MaxBotClient')
    @patch('news.services.max_notifications.OneCNewsRecipientsClient')
    def test_fifth_failed_attempt_is_terminal(self, gateway, bot):
        self.publish(roles=('admin',))
        gateway.return_value.list_recipients.return_value = feed()
        prepare_news_deliveries()
        NewsNotificationDelivery.objects.update(attempts=4)
        bot.return_value.send_message_to_user.side_effect = RuntimeError('provider error')
        self.assertEqual(send_news_deliveries()['failed'], 1)
        self.assertEqual(NewsNotificationDelivery.objects.get().state, 'failed')

    @patch('news.services.max_notifications.MaxBotClient')
    @patch('news.services.max_notifications.OneCNewsRecipientsClient')
    def test_old_pending_and_unprepared_batches_are_discarded_on_reactivation(self, gateway, bot):
        self.publish(title='Устаревшая очередь', roles=('admin',))
        gateway.return_value.list_recipients.return_value = feed()
        self.assertEqual(prepare_news_deliveries()['queued'], 1)
        old_delivery = NewsNotificationDelivery.objects.get()
        unprepared = self.publish(title='Устаревшая неразобранная', roles=('admin',))

        config = MaxNotificationSettings.current()
        config.news_enabled = False
        config.save()
        config.news_enabled = True
        config.save()

        self.assertEqual(prepare_news_deliveries(), {'prepared': 0, 'queued': 0})
        self.assertEqual(send_news_deliveries()['sent'], 0)
        old_delivery.refresh_from_db()
        self.assertEqual(old_delivery.state, NewsNotificationDelivery.State.SKIPPED)
        self.assertIsNotNone(NewsNotificationBatch.objects.get(news=unprepared).prepared_at)
        bot.assert_not_called()
        self.assertEqual(gateway.return_value.list_recipients.call_count, 1)

    @patch('news.services.max_notifications.OneCNewsRecipientsClient')
    def test_reactivation_during_recipient_lookup_does_not_prepare_old_news(self, gateway):
        news = self.publish(roles=('admin',))

        def switch_while_fetching():
            config = MaxNotificationSettings.current()
            config.news_enabled = False
            config.save()
            config.news_enabled = True
            config.save()
            return feed()

        gateway.return_value.list_recipients.side_effect = switch_while_fetching
        self.assertEqual(prepare_news_deliveries(), {'prepared': 0, 'queued': 0})
        self.assertIsNotNone(NewsNotificationBatch.objects.get(news=news).prepared_at)
        self.assertFalse(NewsNotificationDelivery.objects.exists())

    @patch('news.services.max_notifications.MaxBotClient')
    @patch('news.services.max_notifications.OneCNewsRecipientsClient')
    def test_reactivation_during_send_lookup_discards_old_delivery(self, gateway, bot):
        self.publish(roles=('admin',))
        gateway.return_value.list_recipients.return_value = feed()
        prepare_news_deliveries()

        def switch_while_fetching():
            config = MaxNotificationSettings.current()
            config.news_enabled = False
            config.save()
            config.news_enabled = True
            config.save()
            return feed()

        gateway.return_value.list_recipients.side_effect = switch_while_fetching
        self.assertEqual(send_news_deliveries()['sent'], 0)
        self.assertEqual(NewsNotificationDelivery.objects.get().state, 'skipped')
        bot.assert_not_called()


class NewsRecipientsContractTests(SimpleTestCase):
    @override_settings(ONEC_NOTIFICATIONS_SERVICE_KEY='test_' + 'a' * 48)
    @patch('integrations.services.onec_notifications.requests.get')
    def test_validated_service_route_and_secret(self, request):
        request.return_value.status_code = 200
        request.return_value.json.return_value = [
            {'id': OWNER, 'messengerUserId': '12345', 'roles': ['user', 'mechanic']},
        ]
        result = OneCNewsRecipientsClient().list_recipients()
        self.assertEqual(result[OWNER]['roles'], frozenset({'user', 'mechanic'}))
        self.assertTrue(request.call_args.args[0].endswith('/notifications/news/recipients'))
        self.assertEqual(request.call_args.kwargs['headers']['X-ServiceCar-Notifications-Key'],
                         'test_' + 'a' * 48)
        self.assertFalse(request.call_args.kwargs['allow_redirects'])

    @override_settings(ONEC_NOTIFICATIONS_SERVICE_KEY='test_' + 'a' * 48)
    @patch('integrations.services.onec_notifications.requests.get')
    def test_rejects_duplicate_invalid_or_ambiguous_recipients(self, request):
        request.return_value.status_code = 200
        cases = [
            [{'id': OWNER, 'messengerUserId': '123', 'roles': ['user']},
             {'id': MECHANIC, 'messengerUserId': '123', 'roles': ['mechanic']}],
            [{'id': OWNER, 'messengerUserId': 'abc', 'roles': ['user']}],
            [{'id': OWNER, 'messengerUserId': '123', 'roles': ['unknown']}],
            [{'id': OWNER, 'messengerUserId': '123', 'roles': []}],
        ]
        for rows in cases:
            request.return_value.json.return_value = rows
            with self.subTest(rows=rows), self.assertRaises(OneCNotificationError):
                OneCNewsRecipientsClient().list_recipients()

    def test_http_link_is_not_allowed(self):
        with self.assertRaises(ValueError):
            news_url(1, site_url='http://evil.invalid')

    def test_role_access_matches_feed_visibility(self):
        self.assertFalse(can_read_news({'user'}, is_global=False, target_roles={'mechanic'}))
        self.assertTrue(can_read_news({'mechanic'}, is_global=False, target_roles={'user'}))
        self.assertTrue(can_read_news({'admin'}, is_global=False, target_roles={'mechanic'}))
        self.assertTrue(can_read_news({'user'}, is_global=True, target_roles=set()))
