"""Authenticated MAX Webhook. Never expose feedback writes as public REST APIs."""
import hmac
import json
import logging
import re
from datetime import datetime, time, timedelta

from django.conf import settings
from django.db.models import Avg, Count, Q
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from feedback.models import FeedbackInvitation, FeedbackResponse
from feedback.services import process_feedback_callback, process_feedback_text
from notifications.models import MaxNotificationSettings
from orders.views import _statistics_default, _statistics_periods
from users.auth.max.client import MaxBotClient
from users.models import UserRole

logger = logging.getLogger(__name__)


class FeedbackStatisticsView(APIView):
    """Read-only customer feedback dashboard for the active manager role."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        if request.active_role != UserRole.ADMIN:
            raise PermissionDenied('Оценки обслуживания доступны только менеджеру.')

        periods = _statistics_periods()
        default_days = _statistics_default(periods)
        if default_days is None:
            raise ValidationError({'days': 'В Django не настроены доступные периоды статистики.'})
        days = request.query_params.get('days', str(default_days))
        if (days not in {str(item['days']) for item in periods}
                or set(request.query_params) - {'days', 'format'}):
            raise ValidationError({'days': 'Выберите период из списка доступных в настройках Django.'})

        now = timezone.now()
        end_day = timezone.localdate(now)
        start_day = end_day - timedelta(days=int(days) - 1)
        start = timezone.make_aware(
            datetime.combine(start_day, time.min), timezone.get_current_timezone(),
        )
        config = MaxNotificationSettings.current()
        low_max, high_min = config.feedback_low_max, config.feedback_high_min
        responses = FeedbackResponse.objects.filter(
            responded_at__gte=start, responded_at__lte=now,
        )
        totals = responses.aggregate(
            count=Count('pk'), average=Avg('rating'),
            high=Count('pk', filter=Q(rating__gte=high_min)),
            low=Count('pk', filter=Q(rating__lte=low_max)),
        )
        total = totals['count']
        sent_requests = FeedbackInvitation.objects.filter(
            state__in=(FeedbackInvitation.State.SENT, FeedbackInvitation.State.DECLINED),
            sent_at__gte=start, sent_at__lte=now,
        )
        sent_count = sent_requests.count()
        answered_count = sent_requests.filter(response__isnull=False).count()

        distribution_counts = dict(
            responses.values_list('rating').annotate(count=Count('pk'))
        )
        outcomes = []
        for code, label in (('closed', 'Автомобиль выдан'), ('cancelled', 'Заказ отменён')):
            values = responses.filter(invitation__outcome=code).aggregate(
                count=Count('pk'), average=Avg('rating'),
                high=Count('pk', filter=Q(rating__gte=high_min)),
            )
            outcomes.append({
                'code': code, 'label': label, 'count': values['count'],
                'averageRating': round(values['average'] or 0, 2),
                'highPercent': round(values['high'] / values['count'] * 100, 1)
                if values['count'] else 0,
            })

        recent = responses.select_related('invitation').order_by('-responded_at', '-pk')[:10]
        reviews = []
        for item in recent:
            invitation = item.invitation
            reviews.append({
                'orderId': str(invitation.order_id),
                'orderNumber': invitation.order_number,
                'carName': invitation.car_name,
                'outcome': invitation.outcome,
                'rating': item.rating,
                'band': ('low' if item.rating <= low_max else
                         'high' if item.rating >= high_min else 'neutral'),
                'reason': item.get_reason_display() if item.reason else '',
                'comment': item.comment,
                'respondedAt': item.responded_at,
            })

        return Response({
            'period': {'from': start_day.isoformat(), 'to': end_day.isoformat(), 'days': int(days)},
            'thresholds': {'lowMax': low_max, 'highMin': high_min},
            'summary': {
                'ratings': total,
                'averageRating': round(totals['average'] or 0, 2),
                'highPercent': round(totals['high'] / total * 100, 1) if total else 0,
                'lowCount': totals['low'],
                'responseRate': round(answered_count / sent_count * 100, 1) if sent_count else 0,
                'requestsSent': sent_count,
                'responsesToRequests': answered_count,
            },
            'distribution': [
                {'rating': rating, 'count': distribution_counts.get(rating, 0)}
                for rating in range(1, 6)
            ],
            'byOutcome': outcomes,
            'recentReviews': reviews,
        })


@csrf_exempt
@require_POST
def max_feedback_webhook(request):
    secret = settings.MAX_WEBHOOK_SECRET
    if not isinstance(secret, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,256}', secret):
        # No configured secret means the endpoint is closed, not publicly writable.
        return HttpResponse(status=503)
    supplied = request.headers.get('X-Max-Bot-Api-Secret', '')
    if not hmac.compare_digest(supplied, secret):
        return HttpResponse(status=403)
    if len(request.body) > 65536:
        return HttpResponse(status=413)
    try:
        event = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return HttpResponse(status=400)
    if not isinstance(event, dict):
        return HttpResponse(status=400)
    try:
        if event.get('update_type') == 'message_callback':
            result = process_feedback_callback(event)
            if result:
                callback_id, text, attachments = result
                MaxBotClient().answer_callback(
                    callback_id=callback_id, text=text, attachments=attachments,
                )
        elif event.get('update_type') == 'message_created':
            user_id = process_feedback_text(event)
            if user_id:
                try:
                    MaxBotClient().send_message_to_user(
                        user_id=user_id, text='Спасибо! Комментарий к вашей оценке сохранён.',
                    )
                except Exception:
                    # Feedback itself has already been persisted. A retry must
                    # never attach a second comment to a different invitation.
                    logger.warning('MAX feedback comment acknowledgement failed')
    except Exception:
        # MAX may retry. Database writes are idempotent for each invitation.
        logger.warning('MAX feedback webhook processing failed')
        return HttpResponse(status=503)
    return JsonResponse({'ok': True})
