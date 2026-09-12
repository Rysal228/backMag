from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .forms import CustomUserCreationForm,CustomUserChangeForm
from .models import CustomUser

class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = CustomUser

    list_display = (
        'phone',
        'full_name'
    )

    search_fields = (
        'phone',
        'full_name',
    )

    ordering = (
        'phone',
    )

    fieldsets = (
        (None, {'fields': ('phone', 'password')}),
        ('Personal info', {'fields': ('full_name', 'birthday', 'messenger_user_id')}),
        ('Permissions', {
            'fields': (
                'is_active',
                'is_staff',
                'is_superuser',
                'groups',
                'user_permissions',
            ),
        }),
        ('Important dates', {'fields': ('last_login',)}),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': (
                'phone',
                'full_name',
                'birthday',
                'password1',
                'password2',
                'is_staff',
                'is_superuser',
            ),
        }),
    )

admin.site.register(CustomUser, CustomUserAdmin)