from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .forms import CustomUserCreationForm, CustomUserChangeForm
from .models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = CustomUser

    list_display = (
        'phone',
        'last_name',
        'first_name',
        'patronymic',
        'role',
    )

    search_fields = (
        'phone',
        'last_name',
        'first_name',
        'patronymic',
    )

    list_filter = (
        'role',
        'is_active',
    )

    ordering = (
        'last_name',
        'first_name',
    )

    fieldsets = (
        (None, {
            'fields': (
                'phone',
                'password',
            ),
        }),
        ('Personal info', {
            'fields': (
                'last_name',
                'first_name',
                'patronymic',
                'birthday',
                'messenger_user_id',
            ),
        }),
        ('Role', {
            'fields': (
                'role',
            ),
        }),
        ('Permissions', {
            'fields': (
                'is_active',
                'is_staff',
                'is_superuser',
                'groups',
                'user_permissions',
            ),
        }),
        ('Important dates', {
            'fields': (
                'last_login',
            ),
        }),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'phone',
                'last_name',
                'first_name',
                'patronymic',
                'birthday',
                'role',
                'password1',
                'password2',
                'is_staff',
                'is_superuser',
            ),
        }),
    )