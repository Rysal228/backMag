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
        'full_name',
        'role',
    )

    search_fields = (
        'phone',
        'full_name',
    )

    list_filter = (
        'role',
        'is_active',
    )

    ordering = (
        'phone',
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
                'full_name',
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
                'full_name',
                'birthday',
                'role',
                'password1',
                'password2',
                'is_staff',
                'is_superuser',
            ),
        }),
    )