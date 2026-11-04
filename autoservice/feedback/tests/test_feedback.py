"""Isolated 1C/MAX workflow tests. No network calls or live bot credentials."""
import json
from datetime import timedelta
from unittest.mock import patch
from uuid import UUID

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from feedback.models import FeedbackInvitation, FeedbackOrderSnapshot, FeedbackResponse
from feedback.services import (
    invitation_message, observe_feedback_orders, send_feedback_invitations,
)
from notifications.models import MaxNotificationSettings


ORDER = 'c4b40c63-0c41-48ba-bd2e-84e5829ff880'
CAR = '50eaa718-59f6-4bd8-97c0-ab9786685c08'
OWNER = '9ec059a0-5aa6-4c58-b285-12d8b92d04fa'
OTHER = '073f1b97-5be0-40aa-8d97-1fd463d667a8'
MAX_USER = 77335511


def record(status='in_progress', owner=OWNER):
    return {
        'id': ORDER, 'car': CAR, 'ownerId': owner,
        'orderNumber': '00000125', 'carName': 'Lada Vesta',
        'status': {'code': status, 'name': status},
        'workStatus': {'code': 'execution', 'name': 'В работе'},
    }


def recipient(owner=OWNER, eligible=True):
    return {
        'id': ORDER, 'car': CAR, 'ownerId': owner, 'eligible': eligible,
        'messengerUserId': str(MAX_USER) if eligible else '',
    }


def webhook_event(item, action='rate', value='2', user_id=MAX_USER):
    return {
        'update_type': 'message_callback',
        'callback': {
            'callback_id': 'callback-123',
            'payload': f'fb1:{item.token.hex}:{action}:{value}',
            'user': {'user_id': user_id, 'is_bot': False},
        },
    }


@override_settings(
    ONEC_NOTIFICATIONS_SERVICE_KEY='test_' + 'a' * 48,
    MAX_WEBHOOK_SECRET='fake-webhook-secret-with-good-length',
)
class FeedbackTests(TestCase):
    def setUp(self):
        config = MaxNotificationSettings.current()
        config.feedback_enabled = True
        config.feedback_delay_minutes = 45
        config.feedback_low_max = 2
        config.feedback_high_min = 4
        config.save()

    @staticmethod
    def invite(outcome='closed', state=FeedbackInvitation.State.SENT):
        now = timezone.now()
        return FeedbackInvitation.objects.create(
            order_id=ORDER, owner_id=OWNER, car_id=CAR,
            order_number='00000125', car_name='Lada Vesta', outcome=outcome,
            state=state, due_at=now, sent_at=now,
            expires_at=now + timedelta(days=7),
        )

    @patch('feedback.services.OneCNotificationsClient')
    def test_only_terminal_transition_after_baseline_queues_with_shared_delay(self, client):
        client.return_value.list_orders.return_value = [record()]
        self.assertEqual(observe_feedback_orders(), {'baseline': 1, 'queued': 0})
        client.return_value.list_orders.return_value = [record('completed')]
        self.assertEqual(observe_feedback_orders()['queued'], 0)
        before = timezone.now()
        client.return_value.list_orders.return_value = [record('closed')]
        self.assertEqual(observe_feedback_orders()['queued'], 1)
        self.assertEqual(observe_feedback_orders()['queued'], 0)
        invite = FeedbackInvitation.objects.get()
        self.assertEqual(invite.outcome, 'closed')
        self.assertGreaterEqual(invite.due_at, before + timedelta(minutes=45))
        self.assertLess(invite.due_at, timezone.now() + timedelta(minutes=46))

    @patch('feedback.services.OneCNotificationsClient')
    def test_cancelled_is_an_equal_terminal_outcome(self, client):
        client.return_value.list_orders.return_value = [record('under_review')]
        observe_feedback_orders()
        client.return_value.list_orders.return_value = [record('cancelled')]
        self.assertEqual(observe_feedback_orders()['queued'], 1)
        invitation = FeedbackInvitation.objects.get()
        text, _ = invitation_message(invitation)
        self.assertIn('взаимодействие', text)
        self.assertNotIn('довольны результатом', text)

    @patch('feedback.services.OneCNotificationsClient')
    def test_existing_closed_orders_and_owner_change_are_not_surveyed(self, client):
        client.return_value.list_orders.return_value = [record('closed')]
        self.assertEqual(observe_feedback_orders()['queued'], 0)
        client.return_value.list_orders.return_value = [record('in_progress', owner=OTHER)]
        self.assertEqual(observe_feedback_orders()['queued'], 0)
        client.return_value.list_orders.return_value = [record('cancelled', owner=OTHER)]
        self.assertEqual(observe_feedback_orders()['queued'], 1)

    @patch('feedback.services.OneCNotificationsClient')
    def test_reactivation_baselines_old_changes_and_drops_old_pending(self, client):
        client.return_value.list_orders.return_value = [record()]
        observe_feedback_orders()
        waiting = self.invite(state=FeedbackInvitation.State.PENDING)
        cfg = MaxNotificationSettings.current()
        cfg.feedback_enabled = False
        cfg.save()
        cfg.feedback_enabled = True
        cfg.save()
        client.return_value.list_orders.return_value = [record('closed')]
        self.assertEqual(observe_feedback_orders()['queued'], 0)
        waiting.refresh_from_db()
        self.assertEqual(waiting.state, FeedbackInvitation.State.SKIPPED)

    @patch('feedback.services.MaxBotClient')
    @patch('feedback.services.OneCNotificationsClient')
    def test_sends_only_after_due_time_to_live_owner_with_max_buttons(self, client, bot):
        item = self.invite(state=FeedbackInvitation.State.PENDING)
        FeedbackOrderSnapshot.objects.create(
            order_id=ORDER, car_id=CAR, owner_id=OWNER, order_code='closed',
        )
        item.due_at = timezone.now() + timedelta(minutes=1)
        item.save(update_fields=['due_at'])
        self.assertEqual(send_feedback_invitations()['sent'], 0)
        item.due_at = timezone.now() - timedelta(seconds=1)
        item.save(update_fields=['due_at'])
        client.return_value.recipient.return_value = recipient()
        self.assertEqual(send_feedback_invitations()['sent'], 1)
        item.refresh_from_db()
        self.assertIsNotNone(item.expires_at)
        self.assertEqual(item.state, FeedbackInvitation.State.SENT)
        kwargs = bot.return_value.send_message_to_user.call_args.kwargs
        self.assertEqual(kwargs['user_id'], str(MAX_USER))
        self.assertEqual(len(kwargs['attachments'][0]['payload']['buttons'][0]), 5)

    @patch('feedback.services.MaxBotClient')
    @patch('feedback.services.OneCNotificationsClient')
    def test_sender_mismatch_skips_and_provider_error_retries(self, client, bot):
        self.invite(state=FeedbackInvitation.State.PENDING)
        FeedbackOrderSnapshot.objects.create(
            order_id=ORDER, car_id=CAR, owner_id=OWNER, order_code='closed',
        )
        client.return_value.recipient.return_value = recipient(owner=OTHER)
        self.assertEqual(send_feedback_invitations()['skipped'], 1)
        bot.assert_not_called()

    @patch('feedback.views.MaxBotClient')
    @patch('feedback.services.OneCNotificationsClient')
    def test_score_is_saved_once_and_low_reason_and_comment_follow(self, client, bot):
        item = self.invite()
        client.return_value.recipient.return_value = recipient()
        url = reverse('max-feedback-webhook')

        def post(event):
            return self.client.post(
                url, data=json.dumps(event), content_type='application/json',
                HTTP_X_MAX_BOT_API_SECRET='fake-webhook-secret-with-good-length',
            )

        self.assertEqual(post(webhook_event(item)).status_code, 200)
        response = FeedbackResponse.objects.get(invitation=item)
        self.assertEqual(response.rating, 2)
        self.assertEqual(response.rating, 2)
        self.assertIn('не устроило', bot.return_value.answer_callback.call_args.kwargs['text'])
        self.assertEqual(post(webhook_event(item)).status_code, 200)
        self.assertEqual(FeedbackResponse.objects.count(), 1)
        self.assertEqual(post(webhook_event(item, 'reason', 'timing')).status_code, 200)
        self.assertEqual(FeedbackResponse.objects.get().reason, 'timing')
        self.assertEqual(post(webhook_event(item, 'write', 'x')).status_code, 200)

        message = {
            'update_type': 'message_created',
            'message': {
                'sender': {'user_id': MAX_USER, 'is_bot': False},
                'recipient': {'chat_id': MAX_USER},
                'body': {'text': 'Пришлось ждать два часа.'},
            },
        }
        self.assertEqual(post(message).status_code, 200)
        self.assertEqual(post(message).status_code, 200)
        self.assertEqual(FeedbackResponse.objects.get().comment, 'Пришлось ждать два часа.')
        bot.return_value.send_message_to_user.assert_called_once()

    @patch('feedback.views.MaxBotClient')
    @patch('feedback.services.OneCNotificationsClient')
    def test_forged_user_cannot_rate_or_comment(self, client, bot):
        item = self.invite()
        client.return_value.recipient.return_value = recipient()
        result = self.client.post(
            reverse('max-feedback-webhook'), data=json.dumps(webhook_event(item, user_id=999)),
            content_type='application/json',
            HTTP_X_MAX_BOT_API_SECRET='fake-webhook-secret-with-good-length',
        )
        self.assertEqual(result.status_code, 200)
        self.assertFalse(FeedbackResponse.objects.exists())

    def test_invalid_webhook_secret_rejected_even_with_valid_rating(self):
        item = self.invite()
        url = reverse('max-feedback-webhook')
        payload = json.dumps(webhook_event(item))
        self.assertEqual(self.client.post(url, payload, content_type='application/json').status_code, 403)
        with override_settings(MAX_WEBHOOK_SECRET=''):
            self.assertEqual(self.client.post(url, payload, content_type='application/json').status_code, 503)
        self.assertFalse(FeedbackResponse.objects.exists())

    @patch('feedback.views.MaxBotClient')
    @patch('feedback.services.OneCNotificationsClient')
    def test_configured_low_high_ranges_affect_classification(self, client, bot):
        item = self.invite()
        client.return_value.recipient.return_value = recipient()
        result = self.client.post(
            reverse('max-feedback-webhook'),
            data=json.dumps(webhook_event(item, value='3')),
            content_type='application/json',
            HTTP_X_MAX_BOT_API_SECRET='fake-webhook-secret-with-good-length',
        )
        self.assertEqual(result.status_code, 200)
        self.assertEqual(FeedbackResponse.objects.get().rating, 3)
        self.assertIn('Хотите дополнить', bot.return_value.answer_callback.call_args.kwargs['text'])

    @patch('feedback.views.MaxBotClient')
    @patch('feedback.services.OneCNotificationsClient')
    def test_expired_invitation_and_declined_invitation_do_not_accept_scores(self, client, bot):
        item = self.invite()
        client.return_value.recipient.return_value = recipient()
        url = reverse('max-feedback-webhook')

        def click(action, value):
            return self.client.post(
                url, json.dumps(webhook_event(item, action, value)),
                content_type='application/json',
                HTTP_X_MAX_BOT_API_SECRET='fake-webhook-secret-with-good-length',
            )

        item.expires_at = timezone.now() - timedelta(minutes=1)
        item.save(update_fields=['expires_at'])
        self.assertEqual(click('rate', '5').status_code, 200)
        self.assertFalse(FeedbackResponse.objects.exists())

        item.expires_at = timezone.now() + timedelta(days=7)
        item.save(update_fields=['expires_at'])
        self.assertEqual(click('decline', 'x').status_code, 200)
        self.assertEqual(click('rate', '5').status_code, 200)
        self.assertFalse(FeedbackResponse.objects.exists())
        self.assertEqual(FeedbackInvitation.objects.get().state,
                         FeedbackInvitation.State.DECLINED)

    @patch('feedback.views.MaxBotClient')
    @patch('feedback.services.OneCNotificationsClient')
    def test_unrelated_max_messages_are_not_misinterpreted_as_feedback(self, client, bot):
        item = self.invite()
        client.return_value.recipient.return_value = recipient()
        url = reverse('max-feedback-webhook')

        def post(event):
            return self.client.post(
                url, json.dumps(event), content_type='application/json',
                HTTP_X_MAX_BOT_API_SECRET='fake-webhook-secret-with-good-length',
            )

        post(webhook_event(item, value='1'))
        msg = {
            'update_type': 'message_created',
            'message': {'sender': {'user_id': MAX_USER, 'is_bot': False},
                        'recipient': {'chat_id': MAX_USER},
                        'body': {'text': 'Просто сообщение без запроса комментария'}},
        }
        post(msg)
        self.assertEqual(FeedbackResponse.objects.get().comment, '')
        post(webhook_event(item, 'write', 'x'))
        msg['message']['body']['text'] = '/start'
        post(msg)
        self.assertEqual(FeedbackResponse.objects.get().comment, '')
        # Expired comment session may not capture messages even if invite lives.
        FeedbackResponse.objects.update(comment_until=timezone.now() - timedelta(seconds=1))
        msg['message']['body']['text'] = 'Слишком поздно'
        post(msg)
        self.assertEqual(FeedbackResponse.objects.get().comment, '')

    def test_admin_shows_feedback_without_case_management(self):
        config = MaxNotificationSettings.current()
        config.feedback_low_max = 4
        config.feedback_high_min = 4
        with self.assertRaises(ValidationError):
            config.full_clean()
        config.feedback_low_max = 2
        config.feedback_high_min = 4
        config.full_clean()

        account = get_user_model().objects.create_superuser(
            username='feedback-manager', email='manager@example.test', password='unused-test',
        )
        self.client.force_login(account)
        item = self.invite()
        FeedbackResponse.objects.create(invitation=item, rating=1)
        result = self.client.get(reverse('admin:feedback_feedbackresponse_changelist'))
        self.assertEqual(result.status_code, 200)
        self.assertContains(result, 'Средняя')
        self.assertContains(result, 'Низких')
        self.assertContains(result, 'Оценки и отзывы')
        self.assertNotContains(result, 'Рассмотрение обращения')
        self.assertNotContains(result, 'Статус обработки')
        self.assertNotIn('resolution', [field.name for field in FeedbackResponse._meta.fields])

    @patch('feedback.management.commands.poll_feedback_requests.OneCNotificationsClient')
    @patch('feedback.management.commands.poll_feedback_requests.observe_feedback_orders')
    @patch('feedback.management.commands.poll_feedback_requests.send_feedback_invitations')
    def test_command_uses_default_fixed_limit(self, sender, observer, client):
        observer.return_value = {'baseline': 1, 'queued': 0}
        sender.return_value = {'sent': 0, 'skipped': 0, 'retry': 0, 'failed': 0}
        call_command('poll_feedback_requests')
        sender.assert_called_once_with(limit=100)
