from django.contrib import admin
from django.db.models import Avg, Case, CharField, Count, Q, Value, When

from feedback.models import FeedbackInvitation, FeedbackOrderSnapshot, FeedbackResponse
from notifications.models import MaxNotificationSettings


class ImmutableFeedbackAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FeedbackOrderSnapshot)
class FeedbackOrderSnapshotAdmin(ImmutableFeedbackAdmin):
    list_display = ('order_id', 'order_code', 'observed_at')
    search_fields = ('=order_id',)


@admin.register(FeedbackInvitation)
class FeedbackInvitationAdmin(ImmutableFeedbackAdmin):
    list_display = ('order_number', 'outcome', 'state', 'due_at', 'sent_at')
    list_filter = ('outcome', 'state')
    search_fields = ('=order_id', 'order_number')
    readonly_fields = (
        'order_id', 'car_id', 'owner_id', 'order_number', 'car_name',
        'outcome', 'state', 'due_at', 'attempts', 'next_attempt_at',
        'created_at', 'sent_at', 'expires_at',
    )


class RatingBandFilter(admin.SimpleListFilter):
    title = 'Категория оценки'
    parameter_name = 'rating_band'

    def lookups(self, request, model_admin):
        return (('low', 'Низкая'), ('neutral', 'Нейтральная'), ('high', 'Высокая'))

    def queryset(self, request, queryset):
        config = MaxNotificationSettings.current()
        if self.value() == 'low':
            return queryset.filter(rating__lte=config.feedback_low_max)
        if self.value() == 'high':
            return queryset.filter(rating__gte=config.feedback_high_min)
        if self.value() == 'neutral':
            return queryset.filter(rating__gt=config.feedback_low_max,
                                   rating__lt=config.feedback_high_min)
        return queryset


@admin.register(FeedbackResponse)
class FeedbackResponseAdmin(admin.ModelAdmin):
    change_list_template = 'admin/feedback/feedbackresponse/change_list.html'
    list_display = ('order_number', 'rating', 'rating_band', 'reason', 'outcome',
                    'resolution', 'responded_at')
    list_filter = (RatingBandFilter, 'resolution', 'reason', 'invitation__outcome')
    list_editable = ('resolution',)
    search_fields = ('invitation__order_number', '=invitation__order_id')
    list_select_related = ('invitation',)
    readonly_fields = ('invitation', 'rating', 'reason', 'comment', 'responded_at')
    fields = ('invitation', 'rating', 'reason', 'comment', 'responded_at', 'resolution')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description='Заказ')
    def order_number(self, obj):
        return obj.invitation.order_number

    @admin.display(description='Исход')
    def outcome(self, obj):
        return obj.invitation.get_outcome_display()

    @admin.display(description='Категория')
    def rating_band(self, obj):
        return {'low': 'Низкая', 'high': 'Высокая', 'neutral': 'Нейтральная'}[
            obj.feedback_band
        ]

    def get_queryset(self, request):
        config = MaxNotificationSettings.current()
        return super().get_queryset(request).annotate(
            feedback_band=Case(
                When(rating__lte=config.feedback_low_max, then=Value('low')),
                When(rating__gte=config.feedback_high_min, then=Value('high')),
                default=Value('neutral'), output_field=CharField(),
            ),
        )

    def changelist_view(self, request, extra_context=None):
        config = MaxNotificationSettings.current()
        total = FeedbackResponse.objects.count()
        ratings = FeedbackResponse.objects.aggregate(
            average=Avg('rating'),
            positive=Count('id', filter=Q(rating__gte=config.feedback_high_min)),
            negative=Count('id', filter=Q(rating__lte=config.feedback_low_max)),
        )
        delivered = FeedbackInvitation.objects.filter(
            state__in=(FeedbackInvitation.State.SENT, FeedbackInvitation.State.DECLINED),
        ).count()
        # No public review-site formula: this is internal share of high ratings.
        stats = {
            'total': total,
            'average': round(ratings['average'] or 0, 2),
            'high_percent': round((ratings['positive'] or 0) / total * 100, 1) if total else 0,
            'low_count': ratings['negative'] or 0,
            'response_rate': round(total / delivered * 100, 1) if delivered else 0,
        }
        by_outcome = {}
        for code, label in (('closed', 'Выданные автомобили'), ('cancelled', 'Отменённые заказы')):
            rows = FeedbackResponse.objects.filter(invitation__outcome=code).aggregate(
                count=Count('pk'), average=Avg('rating'),
                positive=Count('pk', filter=Q(rating__gte=config.feedback_high_min)),
            )
            by_outcome[code] = {
                'label': label,
                'count': rows['count'],
                'average': round(rows['average'] or 0, 2),
                'high_percent': round(rows['positive'] / rows['count'] * 100, 1)
                if rows['count'] else 0,
            }
        return super().changelist_view(request, {
            **(extra_context or {}), 'feedback_stats': stats,
            'feedback_outcomes': by_outcome,
        })
