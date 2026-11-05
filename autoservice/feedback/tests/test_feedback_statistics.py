"""Manager-only feedback statistics API: no MAX identifiers or callback tokens leak."""
from datetime import timedelta
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIRequestFactory, force_authenticate

from feedback.models import FeedbackInvitation, FeedbackResponse
from feedback.views import FeedbackStatisticsView
from notifications.models import MaxNotificationSettings
from orders.models import StatisticsPeriodOption


class FeedbackStatisticsTests(TestCase):
    def setUp(self):
        StatisticsPeriodOption.objects.all().delete()
        StatisticsPeriodOption.objects.create(days=7, enabled=True, is_default=True)
        StatisticsPeriodOption.objects.create(days=30, enabled=True)
        StatisticsPeriodOption.objects.create(days=90, enabled=False)
        self.account = get_user_model().objects.create_user(username='feedback-api-manager')
        config = MaxNotificationSettings.current()
        config.feedback_low_max = 2
        config.feedback_high_min = 4
        config.save()

    def request(self, role='admin', days=None, page=None):
        params = {} if days is None else {'days': days}
        if page is not None:
            params['page'] = page
        request = APIRequestFactory().get(reverse('feedback-statistics'), params)
        request.active_role = role
        force_authenticate(request, user=self.account)
        return FeedbackStatisticsView.as_view()(request)

    def feedback(self, rating=None, outcome='closed', days_ago=0, state='sent',
                 reason='', comment=''):
        sent = timezone.now() - timedelta(days=days_ago)
        invitation = FeedbackInvitation.objects.create(
            order_id=uuid4(), car_id=uuid4(), owner_id=uuid4(),
            outcome=outcome, order_number=f'0000{FeedbackInvitation.objects.count() + 1}',
            car_name='Lada Vesta', state=state, due_at=sent, sent_at=sent,
        )
        if rating is not None:
            response = FeedbackResponse.objects.create(
                invitation=invitation, rating=rating, reason=reason, comment=comment,
            )
            FeedbackResponse.objects.filter(pk=response.pk).update(responded_at=sent)
        return invitation

    def test_manager_gets_aggregates_distribution_outcomes_and_recent_reviews(self):
        self.feedback(1, comment='Шум после ремонта', reason='quality')
        self.feedback(5, outcome='cancelled', comment='Вопрос урегулирован')
        self.feedback(4)
        self.feedback(None, state='declined')
        self.feedback(None, state='skipped')
        response = self.request()
        self.assertEqual(response.status_code, 200)
        data = response.data
        self.assertEqual(data['period']['days'], 7)
        self.assertEqual(data['summary'], {
            'ratings': 3, 'averageRating': 3.33, 'highPercent': 66.7,
            'lowCount': 1, 'responseRate': 75.0,
            'requestsSent': 4, 'responsesToRequests': 3,
        })
        self.assertEqual([x['count'] for x in data['distribution']], [1, 0, 0, 1, 1])
        self.assertEqual([x['count'] for x in data['byOutcome']], [2, 1])
        self.assertEqual(data['byOutcome'][0]['averageRating'], 2.5)
        self.assertEqual(len(data['recentReviews']), 3)
        self.assertEqual(data['reviewsPagination'], {
            'page': 1, 'pageSize': 6, 'totalCount': 3, 'totalPages': 1,
        })
        self.assertIn('Шум после ремонта', [r['comment'] for r in data['recentReviews']])
        self.assertTrue(any(r['reason'] == 'Качество работ' for r in data['recentReviews']))
        self.assertEqual(data['thresholds'], {'lowMax': 2, 'highMin': 4})
        self.assertNotIn('token', str(data))
        self.assertNotIn('ownerId', str(data))

    def test_period_filters_both_feedback_and_sent_requests(self):
        self.feedback(5, days_ago=10)
        self.feedback(2, days_ago=1)
        short = self.request(days='7').data
        self.assertEqual(short['summary']['ratings'], 1)
        self.assertEqual(short['summary']['requestsSent'], 1)
        long = self.request(days='30').data
        self.assertEqual(long['summary']['ratings'], 2)
        self.assertEqual(long['summary']['requestsSent'], 2)

    def test_thresholds_follow_django_admin_configuration(self):
        self.feedback(3)
        config = MaxNotificationSettings.current()
        config.feedback_low_max = 3
        config.feedback_high_min = 5
        config.save()
        result = self.request().data
        self.assertEqual(result['summary']['lowCount'], 1)
        self.assertEqual(result['summary']['highPercent'], 0)
        self.assertEqual(result['recentReviews'][0]['band'], 'low')

    def test_reviews_are_paginated_without_changing_aggregate_statistics(self):
        for number in range(14):
            self.feedback(5 if number % 2 else 2, comment=f'Отзыв {number}')

        first = self.request(page='1').data
        second = self.request(page='2').data
        third = self.request(page='3').data

        self.assertEqual(first['reviewsPagination'], {
            'page': 1, 'pageSize': 6, 'totalCount': 14, 'totalPages': 3,
        })
        self.assertEqual([len(page['recentReviews']) for page in (first, second, third)], [6, 6, 2])
        self.assertEqual(
            [item['comment'] for page in (first, second, third) for item in page['recentReviews']],
            [f'Отзыв {number}' for number in reversed(range(14))],
        )
        self.assertEqual([page['summary']['ratings'] for page in (first, second, third)], [14] * 3)
        self.assertEqual(self.request(page='99').data['reviewsPagination']['page'], 3)

    def test_forbidden_roles_and_bad_periods(self):
        for role in ('user', 'mechanic'):
            self.assertEqual(self.request(role=role).status_code, 403)
        for days in ('90', '-5', '7&unused=x'):
            self.assertEqual(self.request(days=days).status_code, 400)
        for page in ('0', '-1', 'x', '1.5', '9999999', '²'):
            self.assertEqual(self.request(page=page).status_code, 400)

    def test_no_data_returns_empty_distribution_and_reviews(self):
        result = self.request().data
        self.assertEqual(result['summary']['ratings'], 0)
        self.assertEqual(result['summary']['responseRate'], 0)
        self.assertEqual([item['count'] for item in result['distribution']], [0] * 5)
        self.assertEqual(result['recentReviews'], [])
        self.assertEqual(result['reviewsPagination']['totalPages'], 0)

    def test_anonymous_cannot_access_endpoint(self):
        request = APIRequestFactory().get(reverse('feedback-statistics'))
        response = FeedbackStatisticsView.as_view()(request)
        self.assertIn(response.status_code, (401, 403))
