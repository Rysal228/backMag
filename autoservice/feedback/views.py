"""Authenticated MAX Webhook. Never expose feedback writes as public REST APIs."""
import hmac
import json
import logging
import re

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from feedback.services import process_feedback_callback, process_feedback_text
from users.auth.max.client import MaxBotClient

logger = logging.getLogger(__name__)


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
