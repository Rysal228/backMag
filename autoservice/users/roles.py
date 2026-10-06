from rest_framework.exceptions import ValidationError


class RoleSelectionRequired(ValidationError):
    default_detail = 'Необходимо выбрать роль.'
    default_code = 'role_selection_required'

    def __init__(self, roles):
        super().__init__({
            'code': self.default_code,
            'message': self.default_detail,
            'availableRoles': roles,
        })


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

    raise RoleSelectionRequired(roles)
