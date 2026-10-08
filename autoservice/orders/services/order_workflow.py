from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from orders.models import (
    Order,
    OrderStatus,
    OrderStatusTransition,
    PaymentStatus,
    WorkStatus,
    WorkStatusTransition,
)
from users.models import UserRole


class OrderWorkflowService:
    MANAGER_ROLES = {UserRole.ADMIN}

    @classmethod
    def _role(cls, user):
        role = getattr(user, 'active_role', None)
        if role is None and hasattr(user, 'user'):
            role = getattr(user, 'active_role', None)
        if role is None:
            raise PermissionDenied('Активная роль не определена.')
        return role

    @classmethod
    def can_edit_works(cls, order: Order, user) -> bool:
        role = cls._role(user)
        user_id = user.user.id if hasattr(user, 'user') else user.id
        if role == UserRole.USER:
            return (
                order.status.code == OrderStatus.Code.UNDER_REVIEW
                and order.work_status
                and order.work_status.code == WorkStatus.Code.WAITING_MANAGER_REVIEW
                and order.customer_id == user_id
            )

        return (
            role in cls.MANAGER_ROLES
            and order.status.code == OrderStatus.Code.IN_PROGRESS
            and order.work_status
            and order.work_status.code == WorkStatus.Code.OWNER_APPROVAL
        )

    @classmethod
    def can_edit_price(cls, order: Order, user) -> bool:
        return cls._role(user) in cls.MANAGER_ROLES and cls.can_edit_works(order, user)

    @classmethod
    def can_edit_appointment(cls, order: Order, user) -> bool:
        role = cls._role(user)

        if role == UserRole.USER:
            return (
                order.status.code == OrderStatus.Code.UNDER_REVIEW
                and order.work_status
                and order.work_status.code == WorkStatus.Code.WAITING_MANAGER_REVIEW
                and order.customer_id == user.id
            )

        return (
            role in cls.MANAGER_ROLES
            and order.status.code == OrderStatus.Code.UNDER_REVIEW
            and order.work_status
            and order.work_status.code == WorkStatus.Code.MANAGER_REVIEW
        )

    @classmethod
    def can_assign_mechanics(cls, order: Order, user) -> bool:
        role = cls._role(user)
        return (
            role in cls.MANAGER_ROLES
            and order.status.code == OrderStatus.Code.IN_PROGRESS
        )

    @classmethod
    def can_edit_description(cls, order: Order, user) -> bool:
        role = cls._role(user)
        if role == UserRole.USER:
            return cls.can_edit_works(order, user)
        return role in cls.MANAGER_ROLES and order.status.code != OrderStatus.Code.COMPLETED

    @classmethod
    def can_change_payment(cls, order: Order, user) -> bool:
        return (
            cls._role(user) in cls.MANAGER_ROLES
            and order.status.code == OrderStatus.Code.IN_PROGRESS
            and order.work_status
            and order.work_status.code == WorkStatus.Code.WAITING_PAYMENT
        )

    @classmethod
    def can_transition_status(cls, order: Order, user):
        role = cls._role(user)
        return OrderStatusTransition.objects.filter(
            from_status=order.status,
            to_status__in=cls._available_order_targets(order),
            role=role,
            enabled=True,
        ).exists()

    @classmethod
    def _available_order_targets(cls, order: Order):
        if order.status.code == OrderStatus.Code.UNDER_REVIEW:
            if order.work_status and order.work_status.code == WorkStatus.Code.MANAGER_REVIEW:
                return OrderStatus.objects.filter(
                    code__in=(
                        OrderStatus.Code.IN_PROGRESS,
                        OrderStatus.Code.COMPLETED,
                    )
                )
            return OrderStatus.objects.none()

        if order.status.code == OrderStatus.Code.IN_PROGRESS:
            if order.work_status and order.work_status.code in (
                WorkStatus.Code.EXECUTION,
                WorkStatus.Code.REFUSED,
            ):
                return OrderStatus.objects.filter(code=OrderStatus.Code.COMPLETED)
            return OrderStatus.objects.none()

        return OrderStatus.objects.none()

    @classmethod
    def can_transition_work_status(cls, order: Order, user):
        role = cls._role(user)
        if order.work_status_id is None:
            return False

        return WorkStatusTransition.objects.filter(
            from_status=order.work_status,
            role=role,
            enabled=True,
        ).exists()

    @classmethod
    @transaction.atomic
    def transition_status(cls, order: Order, user, to_status: OrderStatus):
        role = cls._role(user)

        if not OrderStatusTransition.objects.filter(
            from_status=order.status,
            to_status=to_status,
            role=role,
            enabled=True,
        ).exists():
            raise ValidationError({'status': 'Переход заказа в выбранный статус недоступен.'})

        current_work_code = order.work_status.code if order.work_status else None
        target_work_code = None

        if (
            order.status.code == OrderStatus.Code.UNDER_REVIEW
            and to_status.code == OrderStatus.Code.IN_PROGRESS
            and current_work_code == WorkStatus.Code.MANAGER_REVIEW
        ):
            target_work_code = WorkStatus.Code.WAITING_ARRIVAL
        elif (
            order.status.code == OrderStatus.Code.UNDER_REVIEW
            and to_status.code == OrderStatus.Code.COMPLETED
            and current_work_code == WorkStatus.Code.MANAGER_REVIEW
        ):
            target_work_code = WorkStatus.Code.REFUSED
        elif (
            order.status.code == OrderStatus.Code.IN_PROGRESS
            and to_status.code == OrderStatus.Code.COMPLETED
            and current_work_code == WorkStatus.Code.EXECUTION
        ):
            target_work_code = WorkStatus.Code.OWNER_VISIT

        if target_work_code is None:
            raise ValidationError({
                'status': 'Текущий статус работы не позволяет выполнить выбранный переход заказа.'
            })

        target_work = WorkStatus.objects.get(code=target_work_code)
        order.status = to_status
        order.work_status = target_work
        order.save(update_fields=('status', 'work_status'))
        return order

    @classmethod
    @transaction.atomic
    def transition_work_status(cls, order: Order, user, to_status: WorkStatus):
        role = cls._role(user)
        if order.work_status_id is None:
            raise ValidationError({'workStatus': 'У заказа не установлен текущий статус работы.'})

        if not WorkStatusTransition.objects.filter(
            from_status=order.work_status,
            to_status=to_status,
            role=role,
            enabled=True,
        ).exists():
            raise ValidationError({'workStatus': 'Переход статуса работы недоступен.'})

        if (
            order.work_status.code == WorkStatus.Code.WAITING_PAYMENT
            and to_status.code == WorkStatus.Code.EXECUTION
            and (
                order.payment_status is None
                or order.payment_status.code != PaymentStatus.Code.PAID
            )
        ):
            raise ValidationError({
                'paymentStatus': 'Нельзя начать выполнение заказа до его оплаты.'
            })

        order.work_status = to_status
        order.save(update_fields=('work_status',))
        return order

    @classmethod
    def set_payment_status(cls, order: Order, user, status: PaymentStatus):
        if not cls.can_change_payment(order, user):
            raise PermissionDenied('Изменение статуса оплаты недоступно.')
        order.payment_status = status
        order.save(update_fields=('payment_status',))
        return order

    @classmethod
    def permissions(cls, order: Order, user):
        return {
            'canTransitionStatus': cls.can_transition_status(order, user),
            'canTransitionWorkStatus': cls.can_transition_work_status(order, user),
            'canEditWorks': cls.can_edit_works(order, user),
            'canEditPrice': cls.can_edit_price(order, user),
            'canEditAppointment': cls.can_edit_appointment(order, user),
            'canAssignMechanics': cls.can_assign_mechanics(order, user),
            'canEditDescription': cls.can_edit_description(order, user),
            'canChangePaymentStatus': cls.can_change_payment(order, user),
        }
