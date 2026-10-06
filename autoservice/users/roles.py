from rest_framework.exceptions import ValidationError

from .models import UserRole


def get_user_roles(user) -> list[str]:
    return list(
        user.role_assignments.values_list('role', flat=True)
    )


def resolve_active_role(user, role: str | None = None) -> str:
    roles = get_user_roles(user)

    if not roles:
        raise ValidationError({
            'role': 'У пользователя не назначена ни одна роль.',
        })

    if role is not None:
        if role not in roles:
            raise ValidationError({
                'role': 'Выбранная роль недоступна для этого пользователя.',
            })

        return role

    if len(roles) == 1:
        return roles[0]

    raise ValidationError({
        'code': 'role_selection_required',
        'message': 'Необходимо выбрать роль.',
        'details': {
            'availableRoles': roles,
        },
    })
