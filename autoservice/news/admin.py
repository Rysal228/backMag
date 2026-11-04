from django import forms
from django.contrib import admin

from users.models import UserRole

from .models import News, NewsRole, NewsNotificationBatch, NewsNotificationDelivery


class NewsAdminForm(forms.ModelForm):
    roles = forms.MultipleChoiceField(
        label='Роли',
        choices=UserRole.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        help_text='Если включено «Для всех ролей», выбор ролей игнорируется.',
    )

    class Meta:
        model = News
        fields = (
            'title',
            'content',
            'image',
            'is_global',
            'roles',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance.pk:
            self.fields['roles'].initial = list(
                self.instance.role_targets.values_list(
                    'role',
                    flat=True,
                )
            )

    def clean(self):
        cleaned_data = super().clean()

        content = cleaned_data.get('content', '')
        image = cleaned_data.get('image')

        if not content.strip() and not image:
            raise forms.ValidationError(
                'Добавьте текст, изображение или оба варианта.'
            )

        if not cleaned_data.get('is_global') and not cleaned_data.get('roles'):
            self.add_error(
                'roles',
                'Выберите хотя бы одну роль или включите «Для всех ролей».',
            )

        if cleaned_data.get('is_global'):
            cleaned_data['roles'] = []

        return cleaned_data


@admin.register(News)
class NewsAdmin(admin.ModelAdmin):
    form = NewsAdminForm

    list_display = (
        'title',
        'is_global',
        'created_at',
        'updated_at',
    )

    list_filter = (
        'is_global',
    )

    search_fields = (
        'title',
        'content',
    )

    readonly_fields = (
        'created_at',
        'updated_at',
    )

    ordering = (
        '-created_at',
    )

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)

        NewsRole.objects.filter(news=form.instance).delete()

        if not form.cleaned_data.get('is_global'):
            NewsRole.objects.bulk_create(
                [
                    NewsRole(news=form.instance, role=role)
                    for role in form.cleaned_data.get('roles', [])
                ],
            )

        # Admin's change form runs inside a DB transaction: the publication
        # cannot be picked up until both the news and its roles are committed.
        # Edits do not generate a second announcement.
        if not change:
            NewsNotificationBatch.objects.create(
                news=form.instance,
                title=form.instance.title,
                excerpt=form.instance.content,
                is_global=form.instance.is_global,
                roles=list(form.cleaned_data.get('roles', [])),
            )


class ReadOnlyNewsNotificationAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(NewsNotificationBatch)
class NewsNotificationBatchAdmin(ReadOnlyNewsNotificationAdmin):
    list_display = ('title', 'prepared_at', 'created_at')
    search_fields = ('title', '=news__id')
    readonly_fields = ('news', 'title', 'excerpt', 'is_global', 'roles',
                       'created_at', 'prepared_at')


@admin.register(NewsNotificationDelivery)
class NewsNotificationDeliveryAdmin(ReadOnlyNewsNotificationAdmin):
    list_display = ('publication', 'state', 'attempts', 'created_at', 'sent_at')
    list_filter = ('state',)
    search_fields = ('=recipient_id', '=publication__news__id')
    readonly_fields = ('publication', 'recipient_id', 'state', 'attempts',
                       'next_attempt_at', 'created_at', 'sent_at')
