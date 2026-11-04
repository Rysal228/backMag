"""Durable MAX news announcements, routed by live 1C roles and MAX bindings."""
import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from integrations.services.onec_notifications import OneCNewsRecipientsClient
from notifications.models import MaxNotificationSettings, normalize_site_origin
from news.models import NewsNotificationBatch, NewsNotificationDelivery
from users.auth.max.client import MaxBotClient

logger = logging.getLogger(__name__)

# The same hierarchy used by NewsViewSet: an admin reads all role news, a
# mechanic reads user + mechanic news, and an owner reads user news only.
ACCESSIBLE_NEWS_ROLES = {
    'user': frozenset({'user'}),
    'mechanic': frozenset({'user', 'mechanic'}),
    'admin': frozenset({'user', 'mechanic', 'admin'}),
}

MAX_DELIVERY_ATTEMPTS = 5


def can_read_news(recipient_roles, *, is_global, target_roles):
    if is_global:
        return True
    return any(
        ACCESSIBLE_NEWS_ROLES[role].intersection(target_roles)
        for role in recipient_roles
    )


def news_url(news_id, *, site_url=None):
    if site_url is None:
        site_url = MaxNotificationSettings.current().site_url
    base = normalize_site_origin(site_url)
    if not base:
        return ''
    return f'{base}/main?news={news_id}'


def build_message(batch, *, site_url=None):
    title = ' '.join(batch.title.split())[:255]
    # Do not send HTML, arbitrary markup or excessive text to MAX.
    normalized_excerpt = ' '.join(batch.excerpt.split())
    excerpt = normalized_excerpt[:700].rstrip()
    message = f'📰 ServiceCar · Новая новость\n\n{title}'
    if excerpt:
        message += f'\n\n{excerpt}' + ('…' if len(normalized_excerpt) > 700 else '')
    url = news_url(batch.news_id, site_url=site_url)
    if url:
        message += f'\n\nЧитать на сайте: {url}'
    return message


def discard_expired_news_queue(active_since):
    """Retire any work from an earlier activation, including pending retries.

    A paused news channel must never replay publications on reactivation.
    This also handles queue rows left by releases with the older pause policy.
    """
    with transaction.atomic():
        NewsNotificationDelivery.objects.filter(
            publication__created_at__lt=active_since,
            state=NewsNotificationDelivery.State.PENDING,
        ).update(state=NewsNotificationDelivery.State.SKIPPED)
        NewsNotificationBatch.objects.filter(
            created_at__lt=active_since, prepared_at__isnull=True,
        ).update(prepared_at=timezone.now())


def prepare_news_deliveries(limit=20):
    """Expand each new publication once, transactionally; retries are idempotent."""
    config = MaxNotificationSettings.current()
    if not config.news_enabled or config.news_enabled_since is None:
        return {'prepared': 0, 'queued': 0}
    discard_expired_news_queue(config.news_enabled_since)
    ids = list(
        NewsNotificationBatch.objects.filter(
            prepared_at__isnull=True, created_at__gte=config.news_enabled_since,
        )
        .order_by('created_at', 'pk').values_list('pk', flat=True)[:limit]
    )
    if not ids:
        return {'prepared': 0, 'queued': 0}
    # Fetch and validate all 1C recipients before changing any DB rows.
    recipients = OneCNewsRecipientsClient().list_recipients()
    result = {'prepared': 0, 'queued': 0}
    for pk in ids:
        with transaction.atomic():
            batch = (
                NewsNotificationBatch.objects.select_for_update(skip_locked=True)
                .filter(pk=pk, prepared_at__isnull=True).first()
            )
            if batch is None:
                continue
            live_config = MaxNotificationSettings.current()
            if not live_config.news_enabled:
                continue
            if (live_config.news_enabled_since is None
                    or batch.created_at < live_config.news_enabled_since):
                batch.prepared_at = timezone.now()
                batch.save(update_fields=['prepared_at'])
                continue
            eligible = [
                NewsNotificationDelivery(publication=batch, recipient_id=uuid)
                for uuid, recipient in recipients.items()
                if can_read_news(recipient['roles'], is_global=batch.is_global,
                                 target_roles=set(batch.roles))
            ]
            NewsNotificationDelivery.objects.bulk_create(eligible, batch_size=500, ignore_conflicts=True)
            batch.prepared_at = timezone.now()
            batch.save(update_fields=['prepared_at'])
            result['prepared'] += 1
            result['queued'] += len(eligible)
    return result


def send_news_deliveries(limit=100, *, site_url=None):
    """Revalidate active MAX binding and current news visibility before send."""
    if not 1 <= limit <= 1000:
        raise ValueError('Invalid send limit')
    config = MaxNotificationSettings.current()
    if not config.news_enabled or config.news_enabled_since is None:
        return {'sent': 0, 'skipped': 0, 'retry': 0, 'failed': 0}
    discard_expired_news_queue(config.news_enabled_since)
    if site_url is None:
        site_url = config.site_url
    ids = list(
        NewsNotificationDelivery.objects.filter(
            state=NewsNotificationDelivery.State.PENDING,
            next_attempt_at__lte=timezone.now(),
            publication__created_at__gte=config.news_enabled_since,
        ).order_by('created_at', 'pk').values_list('pk', flat=True)[:limit * 3]
    )
    counts = {'sent': 0, 'skipped': 0, 'retry': 0, 'failed': 0}
    if not ids:
        return counts
    recipients = OneCNewsRecipientsClient().list_recipients()
    processed_recipients = set()
    for pk in ids:
        if sum(counts.values()) >= limit:
            break
        with transaction.atomic():
            item = (
                NewsNotificationDelivery.objects.select_for_update(skip_locked=True)
                .select_related('publication__news')
                .filter(pk=pk, state=NewsNotificationDelivery.State.PENDING,
                        next_attempt_at__lte=timezone.now()).first()
            )
            if item is None or item.recipient_id in processed_recipients:
                continue
            batch = item.publication
            live_config = MaxNotificationSettings.current()
            if not live_config.news_enabled:
                break
            processed_recipients.add(item.recipient_id)
            recipient = recipients.get(str(item.recipient_id))
            news = batch.news
            current_roles = set(news.role_targets.values_list('role', flat=True))
            if (
                live_config.news_enabled_since is None
                or batch.created_at < live_config.news_enabled_since
                or recipient is None
                or not can_read_news(recipient['roles'], is_global=batch.is_global,
                                     target_roles=set(batch.roles))
                or not can_read_news(recipient['roles'], is_global=news.is_global,
                                     target_roles=current_roles)
            ):
                item.state = NewsNotificationDelivery.State.SKIPPED
                counts['skipped'] += 1
            else:
                try:
                    MaxBotClient().send_message_to_user(
                        user_id=recipient['messengerUserId'],
                        text=build_message(batch, site_url=site_url),
                    )
                    item.state = NewsNotificationDelivery.State.SENT
                    item.sent_at = timezone.now()
                    counts['sent'] += 1
                except Exception:
                    logger.warning('MAX news delivery failed for queue row %s', pk)
                    item.attempts += 1
                    if item.attempts >= MAX_DELIVERY_ATTEMPTS:
                        item.state = NewsNotificationDelivery.State.FAILED
                        counts['failed'] += 1
                    else:
                        item.next_attempt_at = timezone.now() + timedelta(
                            seconds=min(3600, 60 * (2 ** (item.attempts - 1)))
                        )
                        counts['retry'] += 1
            item.save()
    return counts
