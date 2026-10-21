"""Chat messages remain in Django; their parent order and permissions live in 1C."""
from integrations.services.onec_orders import OneCOrdersClient, OneCOrderError
from users.models import UserRole
from rest_framework.exceptions import PermissionDenied

from chats.models import ChatRoom


def active_role(request):
    role = getattr(request, "active_role", None)
    if role is None:
        raise PermissionDenied("Активная роль не определена.")
    return role


def can_access_order_chats(order, request):
    """Order must have been fetched by OneCOrdersClient for this exact actor."""
    role = active_role(request)
    if role in (UserRole.ADMIN, UserRole.USER):
        return True
    return role == UserRole.MECHANIC and str(request.user.id).lower() in {
        str(uid).lower() for uid in order.get("mechanics", [])
    }


def can_access_room_for(room: ChatRoom, user, role) -> bool:
    if role not in (UserRole.USER, UserRole.ADMIN, UserRole.MECHANIC):
        return False
    try:
        # 1C checks the real order's owner for user and its actual existence.
        order = OneCOrdersClient().get(room.order_id, user.pk, role)
    except OneCOrderError:
        return False

    if room.type == ChatRoom.Type.CUSTOMER_MANAGER:
        return role in (UserRole.USER, UserRole.ADMIN)
    if room.type == ChatRoom.Type.MANAGER_MECHANIC:
        return role == UserRole.ADMIN or (
            role == UserRole.MECHANIC
            and str(room.mechanic_id).lower() == str(user.pk).lower()
            and str(user.pk).lower() in {
                str(uid).lower() for uid in order.get("mechanics", [])
            }
        )
    return False


def can_access_room(room: ChatRoom, request) -> bool:
    return can_access_room_for(room, request.user, active_role(request))
