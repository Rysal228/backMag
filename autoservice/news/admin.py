from django import forms
from django.contrib import admin

from users.models import UserRole

from .models import News, NewsRole


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
