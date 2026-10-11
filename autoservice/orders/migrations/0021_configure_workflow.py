from django.db import migrations


ORDER_STATUS_CODES = {
    'На рассмотрении': 'under_review',
    'В работе': 'in_progress',
    'Завершен': 'completed',
}

WORK_STATUS_CODES = {
    'Ожидание проверки менеджером': 'waiting_manager_review',
    'Проверяется менеджером': 'manager_review',
    'Ожидание прибытия авто в сервис': 'waiting_arrival',
    'Приёмка': 'intake',
    'Согласование с владельцем': 'owner_approval',
    'Ожидание оплаты': 'waiting_payment',
    'Специалисты выполняют заказ': 'execution',
    'Владелец должен явиться в сервис': 'owner_visit',
    'Отказано': 'refused',
}


def configure_workflow(apps, schema_editor):
    OrderStatus = apps.get_model('orders', 'OrderStatus')
    WorkStatus = apps.get_model('orders', 'WorkStatus')
    OrderStatusTransition = apps.get_model('orders', 'OrderStatusTransition')
    WorkStatusTransition = apps.get_model('orders', 'WorkStatusTransition')
    PaymentStatus = apps.get_model('orders', 'PaymentStatus')
    Order = apps.get_model('orders', 'Order')

    for name, code in ORDER_STATUS_CODES.items():
        OrderStatus.objects.filter(name=name).update(code=code)

    for name, code in WORK_STATUS_CODES.items():
        WorkStatus.objects.filter(name=name).update(code=code)

    unpaid = PaymentStatus.objects.get(code='unpaid')
    Order.objects.filter(payment_status__isnull=True).update(payment_status=unpaid)

    statuses = {
        status.code: status
        for status in OrderStatus.objects.filter(code__isnull=False)
    }
    work_statuses = {
        status.code: status
        for status in WorkStatus.objects.filter(code__isnull=False)
    }

    manager_roles = ('admin',)

    order_transitions = (
        ('under_review', 'in_progress'),
        ('under_review', 'completed'),
        ('in_progress', 'completed'),
    )
    for source, target in order_transitions:
        if source in statuses and target in statuses:
            for role in manager_roles:
                OrderStatusTransition.objects.get_or_create(
                    from_status=statuses[source], to_status=statuses[target], role=role,
                    defaults={'enabled': True},
                )

    work_transitions = (
        ('waiting_manager_review', 'manager_review'),
        ('manager_review', 'waiting_arrival'),
        ('manager_review', 'owner_visit'),
        ('waiting_arrival', 'intake'),
        ('intake', 'owner_approval'),
        ('owner_approval', 'waiting_payment'),
        ('owner_approval', 'refused'),
        ('waiting_payment', 'execution'),
    )
    for source, target in work_transitions:
        if source in work_statuses and target in work_statuses:
            for role in manager_roles:
                WorkStatusTransition.objects.get_or_create(
                    from_status=work_statuses[source], to_status=work_statuses[target], role=role,
                    defaults={'enabled': True},
                )


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0020_order_workflow_foundation'),
    ]

    operations = [
        migrations.RunPython(configure_workflow, migrations.RunPython.noop),
    ]
