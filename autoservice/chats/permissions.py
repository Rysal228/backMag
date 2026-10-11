from rest_framework.exceptions import PermissionDenied

from chats.models import ChatRoom
from users.models import UserRole


def active_role(request):
    role = getattr(request, 'active_role', None)
    if role is None:
        raise PermissionDenied('Активная роль не определена.')
    return role


def can_access_order_chats(order, request):
    role = active_role(request)
    user = request.user

    if role == UserRole.USER:
        return order.customer_id == user.id

    if role == UserRole.ADMIN:
        return True

    if role == UserRole.MECHANIC:
        return order.mechanics.filter(pk=user.pk).exists()

    return False


def can_access_room_for(room: ChatRoom, user, role) -> bool:
    if room.type == ChatRoom.Type.CUSTOMER_MANAGER:
        return (
            (role == UserRole.USER and room.order.customer_id == user.id)
            or role == UserRole.ADMIN
        )

    if room.type == ChatRoom.Type.MANAGER_MECHANIC:
        return (
            role == UserRole.ADMIN
            or (
                role == UserRole.MECHANIC
                and room.mechanic_id == user.id
                and room.order.mechanics.filter(pk=user.pk).exists()
            )
        )

    return False


def can_access_room(room: ChatRoom, request) -> bool:
    return can_access_room_for(room, request.user, active_role(request))
