import hashlib
import hmac
import logging
import re
from datetime import timedelta
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from feedback.models import FeedbackInvitation, FeedbackOrderSnapshot, FeedbackResponse
from integrations.services.onec_notifications import OneCNotificationsClient
from notifications.models import MaxNotificationSettings
from orders.services.max_notifications import safe_label
from users.auth.max.client import MaxBotClient

logger = logging.getLogger(__name__)

TERMINAL = frozenset({'closed', 'cancelled'})
REPLY_WINDOW = timedelta(days=7)
COMMENT_WINDOW = timedelta(minutes=15)
MAX_ATTEMPTS = 5
TOKEN_FORMAT = re.compile(r'fb1:([0-9a-f]{32}):(rate|reason|write|done|decline):([a-z0-9_]+)\Z')


def _payload(item, action, value='x'):
    return f'fb1:{item.token.hex}:{action}:{value}'


def _keyboard(rows):
    return [{'type': 'inline_keyboard', 'payload': {'buttons': rows}}]


def _button(item, label, action, value='x'):
    return {'type': 'callback', 'text': label, 'payload': _payload(item, action, value)}


def invitation_message(item):
    if item.outcome == 'cancelled':
        prompt = 'Оцените, пожалуйста, общение и взаимодействие с нашим сервисом.'
    else:
        prompt = 'Насколько вы довольны результатом обслуживания?'
    text = (
        f'🚘 ServiceCar · Заказ №{safe_label(item.order_number, 100)}\n'
        f'{safe_label(item.car_name, 180)}\n\n{prompt}\n\n'
        '1 — очень плохо, 5 — отлично.'
    )
    buttons = [[_button(item, f'{n} ★', 'rate', str(n)) for n in range(1, 6)],
               [_button(item, 'Не хочу оценивать', 'decline')]]
    return text, _keyboard(buttons)


def discard_previous_activation(config):
    if config.feedback_enabled_since:
        FeedbackInvitation.objects.filter(
            state=FeedbackInvitation.State.PENDING,
            created_at__lt=config.feedback_enabled_since,
        ).update(state=FeedbackInvitation.State.SKIPPED)


def observe_feedback_orders():
    config = MaxNotificationSettings.current()
    if not config.feedback_enabled or config.feedback_enabled_since is None:
        return {'baseline': 0, 'queued': 0}
    orders = OneCNotificationsClient().list_orders()
    totals = {'baseline': 0, 'queued': 0}
    for order in orders:
        if not order.get('ownerId'):
            continue
        code = safe_label(order['status']['code'], 80)
        order_id = order['id']
        with transaction.atomic():
            state, created = FeedbackOrderSnapshot.objects.get_or_create(
                order_id=order_id,
                defaults={
                    'car_id': order['car'], 'owner_id': order['ownerId'],
                    'order_code': code,
                },
            )
            if created:
                totals['baseline'] += 1
                continue
            state = FeedbackOrderSnapshot.objects.select_for_update().get(pk=order_id)
            previous = state.order_code
            unchanged_owner = (
                str(state.owner_id) == order['ownerId']
                and str(state.car_id) == order['car']
            )

            fresh = state.observed_at >= config.feedback_enabled_since
            if (fresh and unchanged_owner and previous != code
                    and previous not in TERMINAL and code in TERMINAL):
                _, queued = FeedbackInvitation.objects.get_or_create(
                    order_id=order_id,
                    defaults={
                        'car_id': order['car'], 'owner_id': order['ownerId'],
                        'outcome': code,
                        'order_number': safe_label(order['orderNumber'], 100),
                        'car_name': safe_label(order['carName'], 180),
                        'due_at': timezone.now() + timedelta(minutes=config.feedback_delay_minutes),
                    },
                )
                totals['queued'] += int(queued)
            state.car_id = order['car']
            state.owner_id = order['ownerId']
            state.order_code = code
            state.save()
    discard_previous_activation(config)
    return totals


def _recipient_for(item):
    recipient = OneCNotificationsClient().recipient(str(item.order_id))
    if (recipient is None or not recipient['eligible']
            or recipient['car'] != str(item.car_id)
            or recipient['ownerId'] != str(item.owner_id)):
        return None
    return recipient['messengerUserId']


def send_feedback_invitations(limit=100):
    if not 1 <= limit <= 1000:
        raise ValueError('Invalid feedback limit')
    config = MaxNotificationSettings.current()
    counts = {'sent': 0, 'skipped': 0, 'retry': 0, 'failed': 0}
    if not config.feedback_enabled or config.feedback_enabled_since is None:
        return counts
    discard_previous_activation(config)
    now = timezone.now()
    ids = list(FeedbackInvitation.objects.filter(
        state=FeedbackInvitation.State.PENDING,
        created_at__gte=config.feedback_enabled_since,
        due_at__lte=now,
        next_attempt_at__lte=now,
    ).order_by('due_at', 'pk').values_list('pk', flat=True)[:limit * 3])
    processed_owners = set()
    for pk in ids:
        if sum(counts.values()) >= limit:
            break
        with transaction.atomic():
            item = FeedbackInvitation.objects.select_for_update(skip_locked=True).filter(
                pk=pk, state=FeedbackInvitation.State.PENDING,
                due_at__lte=timezone.now(), next_attempt_at__lte=timezone.now(),
            ).first()
            if item is None or item.owner_id in processed_owners:
                continue
            live = MaxNotificationSettings.current()
            if not live.feedback_enabled:
                break
            if live.feedback_enabled_since is None or item.created_at < live.feedback_enabled_since:
                item.state = FeedbackInvitation.State.SKIPPED
                counts['skipped'] += 1
            elif not FeedbackOrderSnapshot.objects.filter(
                order_id=item.order_id, owner_id=item.owner_id, car_id=item.car_id,
                order_code=item.outcome,
            ).exists():
                item.state = FeedbackInvitation.State.SKIPPED
                counts['skipped'] += 1
            else:
                processed_owners.add(item.owner_id)
                try:
                    max_id = _recipient_for(item)
                    if not max_id:
                        item.state = FeedbackInvitation.State.SKIPPED
                        counts['skipped'] += 1
                    else:
                        body, attachments = invitation_message(item)
                        MaxBotClient().send_message_to_user(
                            user_id=max_id, text=body, attachments=attachments,
                        )
                        item.sent_at = timezone.now()
                        item.expires_at = item.sent_at + REPLY_WINDOW
                        item.state = FeedbackInvitation.State.SENT
                        counts['sent'] += 1
                except Exception:
                    logger.warning('MAX feedback invitation failed for row %s', pk)
                    item.attempts += 1
                    if item.attempts >= MAX_ATTEMPTS:
                        item.state = FeedbackInvitation.State.FAILED
                        counts['failed'] += 1
                    else:
                        item.next_attempt_at = timezone.now() + timedelta(
                            seconds=min(3600, 60 * 2 ** (item.attempts - 1)),
                        )
                        counts['retry'] += 1
            item.save()
    return counts


def _user_digest(user_id):
    return hmac.new(settings.SECRET_KEY.encode(), user_id.encode(), hashlib.sha256).hexdigest()


def _reason_keyboard(item):
    choices = ([
        ('Сроки', 'timing'), ('Стоимость', 'price'),
        ('Общение', 'communication'), ('Личные причины', 'customer_cancel'),
        ('Другое', 'other'),
    ] if item.outcome == 'cancelled' else [
        ('Качество работ', 'quality'), ('Сроки', 'timing'),
        ('Стоимость', 'price'), ('Общение', 'communication'), ('Другое', 'other'),
    ])
    return _keyboard([
        [_button(item, label, 'reason', value) for label, value in choices[:2]],
        [_button(item, label, 'reason', value) for label, value in choices[2:4]],
        [_button(item, choices[4][0], 'reason', choices[4][1])],
        [_button(item, '✍️ Написать комментарий', 'write'), _button(item, 'Готово', 'done')],
    ])


def _write_keyboard(item):
    return _keyboard([[_button(item, '✍️ Написать комментарий', 'write'),
                       _button(item, 'Готово', 'done')]])


def process_feedback_callback(update):
    callback = update.get('callback') or {}
    if not isinstance(callback, dict):
        return None
    payload, callback_id = callback.get('payload'), callback.get('callback_id')
    user = callback.get('user') or {}
    match = TOKEN_FORMAT.fullmatch(payload) if isinstance(payload, str) else None
    if (not match or not isinstance(callback_id, str) or not callback_id
            or not isinstance(user, dict) or type(user.get('user_id')) is not int
            or user.get('is_bot') is True):
        return None
    token, action, value = match.groups()
    user_id = str(user['user_id'])
    result = (callback_id, 'Это приглашение больше недоступно.', [])
    with transaction.atomic():
        item = FeedbackInvitation.objects.select_for_update().filter(token=UUID(hex=token)).first()
        if item is None or item.state != FeedbackInvitation.State.SENT:
            return result
        if item.expires_at is None or timezone.now() > item.expires_at:
            return result
        if _recipient_for(item) != user_id:
            return result
        try:
            response = FeedbackResponse.objects.select_for_update().get(invitation=item)
        except FeedbackResponse.DoesNotExist:
            response = None

        if action == 'decline' and response is None:
            item.state = FeedbackInvitation.State.DECLINED
            item.save(update_fields=['state'])
            return callback_id, 'Спасибо за потраченное время!', []
        if action == 'rate':
            if value not in ('1', '2', '3', '4', '5'):
                return result
            if response is not None:
                if response.comment:
                    return callback_id, 'Спасибо! Оценка и комментарий отправлены.', []
                if response.reason:
                    return callback_id, 'Ваша оценка сохранена. Хотите добавить комментарий?', _write_keyboard(item)
                config = MaxNotificationSettings.current()
                if response.rating <= config.feedback_low_max:
                    return callback_id, 'Оценка сохранена. Что именно вас не устроило?', _reason_keyboard(item)
                return callback_id, 'Ваша оценка сохранена. Хотите добавить комментарий?', _write_keyboard(item)
            rating = int(value)
            config = MaxNotificationSettings.current()
            response = FeedbackResponse.objects.create(
                invitation=item, rating=rating,
                resolution=(FeedbackResponse.Resolution.NEW if rating <= config.feedback_low_max
                            else FeedbackResponse.Resolution.RESOLVED),
            )
            if rating <= config.feedback_low_max:
                return (callback_id,
                        f'Спасибо, оценка {rating}/5 сохранена. Что именно вас не устроило?',
                        _reason_keyboard(item))
            if rating >= config.feedback_high_min:
                message = f'Спасибо за высокую оценку {rating}/5! Хотите дополнить её комментарием?'
            else:
                message = f'Спасибо! Ваша оценка {rating}/5 сохранена. Хотите дополнить её комментарием?'
            return callback_id, message, _write_keyboard(item)
        if response is None:
            return result
        if action == 'reason':
            choices = {choice.value for choice in FeedbackResponse.Reason}
            if value not in choices:
                return result
            if item.outcome == 'cancelled' and value == 'quality':
                return result
            if response.reason:
                return callback_id, 'Причина уже сохранена. Хотите добавить комментарий?', _write_keyboard(item)
            response.reason = value
            response.save(update_fields=['reason'])
            return callback_id, 'Спасибо, причина сохранена. Хотите добавить комментарий?', _write_keyboard(item)
        if action == 'write':
            if response.comment:
                return callback_id, 'Ваш комментарий уже получен. Спасибо!', []
            FeedbackResponse.objects.filter(comment_user_digest=_user_digest(user_id)).update(
                comment_user_digest='', comment_until=None,
            )
            response.comment_user_digest = _user_digest(user_id)
            response.comment_until = min(timezone.now() + COMMENT_WINDOW, item.expires_at)
            response.save(update_fields=['comment_user_digest', 'comment_until'])
            return (callback_id,
                    'Оставьте, пожалуйста, следующим сообщением ваш отзыв. '
                    'На ответ есть 15 минут.', [])
        if action == 'done':
            response.comment_user_digest = ''
            response.comment_until = None
            response.save(update_fields=['comment_user_digest', 'comment_until'])
            return callback_id, 'Спасибо за обратную связь! Ваша оценка сохранена.', []
    return result


def process_feedback_text(update):
    message = update.get('message') or {}
    sender = message.get('sender') or {}
    body = message.get('body') or {}
    recipient = message.get('recipient') or {}
    if not all(isinstance(row, dict) for row in (message, sender, body, recipient)):
        return None
    user_id, text = sender.get('user_id'), body.get('text')
    if (type(user_id) is not int or sender.get('is_bot') is True
            or not isinstance(text, str) or not text.strip()
            or not isinstance(recipient.get('chat_id'), int)):
        return None
    if text.lstrip().startswith('/'):
        return None
    digest = _user_digest(str(user_id))
    with transaction.atomic():
        response = FeedbackResponse.objects.select_for_update().select_related('invitation').filter(
            comment_user_digest=digest,
            comment_until__gt=timezone.now(),
            comment='',
        ).order_by('-responded_at').first()
        if response is None:
            return None
        item = response.invitation
        if (item.state != FeedbackInvitation.State.SENT
                or item.expires_at is None or timezone.now() > item.expires_at
                or _recipient_for(item) != str(user_id)):
            return None
        response.comment = text.strip()[:1000]
        response.comment_user_digest = ''
        response.comment_until = None
        response.save(update_fields=['comment', 'comment_user_digest', 'comment_until'])
    return str(user_id)
