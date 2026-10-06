from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .forms import CustomUserCreationForm, CustomUserChangeForm
from .models import CustomUser, UserRoleAssignment


class UserRoleAssignmentInline(admin.TabularInline):
    model = UserRoleAssignment
    extra = 1
    min_num = 1
    fields = ('role',)


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    add_form = CustomUserCreationForm
    form = CustomUserChangeForm
    model = CustomUser
    inlines = (UserRoleAssignmentInline,)

    list_display = (
        'phone',
        'last_name',
        'first_name',
        'patronymic',
        'display_roles',
    )

    search_fields = (
        'phone',
        'last_name',
        'first_name',
        'patronymic',
    )

    list_filter = (
        'role_assignments__role',
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
                'password1',
                'password2',
                'is_staff',
                'is_superuser',
            ),
        }),
    )

    @admin.display(description='Роли')
    def display_roles(self, obj):
        return ', '.join(
            obj.role_assignments.values_list('role', flat=True)
        )
