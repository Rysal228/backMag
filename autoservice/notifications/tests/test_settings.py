import importlib
import os
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from notifications.models import MaxNotificationSettings, normalize_site_origin
from orders.models import OrderNotificationDelivery


class SiteOriginTests(SimpleTestCase):
    def test_only_https_site_origin_is_allowed(self):
        self.assertEqual(normalize_site_origin(' https://www.cherser-car.site/ '),
                         'https://www.cherser-car.site')
        for value in (
            'http://www.cherser-car.site',
            'https://user:password@www.cherser-car.site',
            'https://www.cherser-car.site/path',
            'https://www.cherser-car.site?next=evil',
            'https://www.cherser-car.site#anchor',
            'https://www.cherser-car.site:invalid',
        ):
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_site_origin(value)


class MaxNotificationSettingsTests(TestCase):
    def test_singleton_and_model_validation(self):
        config = MaxNotificationSettings.current()
        self.assertEqual(config.pk, 1)
        self.assertEqual(MaxNotificationSettings.current().pk, 1)
        with self.assertRaises(ValueError):
            MaxNotificationSettings(pk=2).save()

        config.site_url = 'http://insecure.invalid'
        with self.assertRaises(ValidationError):
            config.full_clean()
        config.site_url = 'https://www.cherser-car.site/'
        config.full_clean()
        self.assertEqual(config.site_url, 'https://www.cherser-car.site')

    def test_news_activation_timestamp_updates_only_on_switch(self):
        config = MaxNotificationSettings.current()
        self.assertIsNone(config.news_enabled_since)
        before = timezone.now()
        config.news_enabled = True
        config.save(update_fields=['news_enabled'])
        config.refresh_from_db()
        first = config.news_enabled_since
        self.assertGreaterEqual(first, before)

        config.site_url = 'https://www.cherser-car.site'
        config.save(update_fields=['site_url'])
        config.refresh_from_db()
        self.assertEqual(config.news_enabled_since, first)

        config.news_enabled = False
        config.save()
        config.refresh_from_db()
        self.assertIsNone(config.news_enabled_since)

        config.news_enabled = True
        config.save()
        config.refresh_from_db()
        self.assertGreater(config.news_enabled_since, first)

    def test_initial_data_migration_copies_existing_env_once(self):
        MaxNotificationSettings.objects.filter(pk=1).delete()
        seed = importlib.import_module(
            'notifications.migrations.0001_initial',
        ).seed_existing_settings
        with patch.dict(os.environ, {
            'MAX_ORDER_NOTIFICATIONS_ENABLED': '1',
            'MAX_NEWS_NOTIFICATIONS_ENABLED': 'true',
            'MAX_ORDER_NOTIFICATIONS_PUBLIC_URL': 'https://www.cherser-car.site/',
        }):
            seed(apps, SimpleNamespace(connection=connection))
        config = MaxNotificationSettings.current()
        self.assertTrue(config.orders_enabled)
        self.assertTrue(config.news_enabled)
        self.assertIsNotNone(config.news_enabled_since)
        self.assertEqual(config.site_url, 'https://www.cherser-car.site')
        with patch.dict(os.environ, {'MAX_ORDER_NOTIFICATIONS_ENABLED': '0'}):
            seed(apps, SimpleNamespace(connection=connection))
        config.refresh_from_db()
        self.assertTrue(config.orders_enabled)  # no later env override

    def test_missing_row_recreated_safely_disabled(self):
        MaxNotificationSettings.objects.filter(pk=1).delete()
        config = MaxNotificationSettings.current()
        self.assertFalse(config.orders_enabled)
        self.assertFalse(config.news_enabled)

    @patch('orders.management.commands.poll_order_notifications.OneCNotificationsClient')
    def test_paused_order_worker_leaves_queue_alone(self, client):
        MaxNotificationSettings.objects.filter(pk=1).update(orders_enabled=False)
        OrderNotificationDelivery.objects.create(
            order_id='4a1c96c9-61cc-4b9f-a215-8f85c61fcb07',
            car_id='0ce3b354-64b7-4601-b593-fcfb23de5592',
            owner_id='1b738f3d-d8bd-4873-9fc1-6be7a87b9043',
            revision=1, order_number='125', car_name='Toyota', order_code='in_progress',
            order_changed=True,
        )
        call_command('poll_order_notifications')
        self.assertEqual(OrderNotificationDelivery.objects.get().state, 'pending')
        client.assert_not_called()

    @override_settings(ONEC_NOTIFICATIONS_SERVICE_KEY='test_' + 'a' * 48)
    @patch('orders.management.commands.poll_order_notifications.send_pending_notifications')
    @patch('orders.management.commands.poll_order_notifications.poll_order_statuses')
    @patch('orders.management.commands.poll_order_notifications.OneCNotificationsClient')
    def test_order_command_uses_fixed_default_limit_and_live_site_url(self, client, poll, send):
        MaxNotificationSettings.objects.filter(pk=1).update(
            orders_enabled=True,
            site_url='https://www.cherser-car.site',
        )
        poll.return_value = {'baseline': 0, 'queued': 0, 'unmapped': 0}
        send.return_value = {'sent': 0, 'skipped': 0, 'retry': 0, 'failed': 0}
        call_command('poll_order_notifications')
        send.assert_called_once_with(
            limit=100, site_url='https://www.cherser-car.site',
        )
        client.assert_called_once()

    @override_settings(ONEC_NOTIFICATIONS_SERVICE_KEY='test_' + 'a' * 48)
    @patch('news.management.commands.poll_news_notifications.send_news_deliveries')
    @patch('news.management.commands.poll_news_notifications.prepare_news_deliveries')
    @patch('news.management.commands.poll_news_notifications.OneCNewsRecipientsClient')
    def test_news_command_uses_fixed_default_limit_and_live_site_url(self, client, prepare, send):
        config = MaxNotificationSettings.current()
        config.news_enabled = True
        config.site_url = 'https://www.cherser-car.site'
        config.save()
        prepare.return_value = {'prepared': 0, 'queued': 0}
        send.return_value = {'sent': 0, 'skipped': 0, 'retry': 0, 'failed': 0}
        call_command('poll_news_notifications')
        send.assert_called_once_with(
            limit=100, site_url='https://www.cherser-car.site',
        )
        client.assert_called_once()

    @override_settings(ONEC_NOTIFICATIONS_SERVICE_KEY='test_' + 'a' * 48)
    @patch('news.management.commands.poll_news_notifications.send_news_deliveries')
    @patch('news.management.commands.poll_news_notifications.prepare_news_deliveries')
    @patch('news.management.commands.poll_news_notifications.OneCNewsRecipientsClient')
    def test_explicit_cli_limit_still_supported(self, client, prepare, send):
        config = MaxNotificationSettings.current()
        config.news_enabled = True
        config.save()
        prepare.return_value = {'prepared': 0, 'queued': 0}
        send.return_value = {'sent': 0, 'skipped': 0, 'retry': 0, 'failed': 0}
        call_command('poll_news_notifications', limit=12)
        send.assert_called_once_with(limit=12, site_url='')


class MaxNotificationAdminTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username='news-admin', email='admin@example.test', password='not-a-real-password',
        )
        self.client.force_login(self.user)

    def test_admin_opens_single_settings_form(self):
        url = reverse('admin:notifications_maxnotificationsettings_changelist')
        response = self.client.get(url)
        self.assertRedirects(
            response, reverse('admin:notifications_maxnotificationsettings_change', args=[1]),
        )
        response = self.client.get(response.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Уведомления о статусах заказов')
        self.assertContains(response, 'Уведомления о новых публикациях')
        self.assertContains(response, 'Оценки и отзывы через MAX')
        self.assertContains(response, 'Запросить оценку через')
        self.assertNotContains(response, 'Приглашения оценить обслуживание')
        self.assertNotContains(response, 'Сообщений за запуск')
        self.assertNotContains(response, 'Попыток доставки')

    def test_admin_saves_without_restart_and_rejects_second_record(self):
        change_url = reverse('admin:notifications_maxnotificationsettings_change', args=[1])
        result = self.client.post(change_url, {
            'orders_enabled': 'on', 'news_enabled': 'on',
            'feedback_delay_minutes': '45', 'feedback_low_max': '2',
            'feedback_high_min': '4', 'feedback_enabled': 'on',
            'site_url': 'https://www.cherser-car.site/',
            '_save': 'Сохранить',
        })
        self.assertEqual(result.status_code, 302)
        config = MaxNotificationSettings.current()
        self.assertTrue(config.orders_enabled)
        self.assertTrue(config.news_enabled)
        self.assertTrue(config.feedback_enabled)
        self.assertIsNotNone(config.feedback_enabled_since)
        self.assertEqual(config.feedback_delay_minutes, 45)
        self.assertEqual((config.feedback_low_max, config.feedback_high_min), (2, 4))
        self.assertIsNotNone(config.news_enabled_since)
        self.assertEqual(config.site_url, 'https://www.cherser-car.site')
        self.assertEqual(MaxNotificationSettings.objects.count(), 1)
        add_url = reverse('admin:notifications_maxnotificationsettings_add')
        self.assertEqual(self.client.get(add_url).status_code, 403)
        delete_url = reverse('admin:notifications_maxnotificationsettings_delete', args=[1])
        self.assertEqual(self.client.get(delete_url).status_code, 403)

    def test_admin_rejects_insecure_url(self):
        change_url = reverse('admin:notifications_maxnotificationsettings_change', args=[1])
        result = self.client.post(change_url, {
            'orders_enabled': 'on', 'news_enabled': 'on',
            'feedback_delay_minutes': '30', 'feedback_low_max': '3',
            'feedback_high_min': '4',
            'site_url': 'http://untrusted.example.com',
            '_save': 'Сохранить',
        })
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, 'Укажите HTTPS-адрес сайта')
        config = MaxNotificationSettings.current()
        self.assertEqual(config.site_url, '')
