from django.db import migrations


def configure_workflow(apps, schema_editor):
    OrderStatus = apps.get_model('orders', 'OrderStatus')
    WorkStatus = apps.get_model('orders', 'WorkStatus')
    OrderStatusTransition = apps.get_model('orders', 'OrderStatusTransition')
    WorkStatusTransition = apps.get_model('orders', 'WorkStatusTransition')

    admin_role = 'admin'

    statuses = {
        status.code: status
        for status in OrderStatus.objects.filter(code__isnull=False)
    }
    work_statuses = {
        status.code: status
        for status in WorkStatus.objects.filter(code__isnull=False)
    }

    # Rebuild the seeded workflow so that changes made in previous migrations
    # cannot leave obsolete transitions in the database.
    OrderStatusTransition.objects.filter(role=admin_role).delete()
    WorkStatusTransition.objects.filter(role=admin_role).delete()

    order_transitions = (
        ('under_review', 'in_progress'),
        ('under_review', 'completed'),
        ('in_progress', 'completed'),
    )

    for source, target in order_transitions:
        if source in statuses and target in statuses:
            OrderStatusTransition.objects.create(
                from_status=statuses[source],
                to_status=statuses[target],
                role=admin_role,
                enabled=True,
            )

    # Work statuses are progressed inside the corresponding order stage.
    # Final work statuses (refused / owner_visit) are assigned together with
    # the transition of the order itself to "completed".
    work_transitions = (
        ('waiting_manager_review', 'manager_review'),
        ('waiting_arrival', 'intake'),
        ('intake', 'owner_approval'),
        ('owner_approval', 'waiting_payment'),
        ('waiting_payment', 'execution'),
    )

    for source, target in work_transitions:
        if source in work_statuses and target in work_statuses:
            WorkStatusTransition.objects.create(
                from_status=work_statuses[source],
                to_status=work_statuses[target],
                role=admin_role,
                enabled=True,
            )


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0022_admin_only_workflow'),
    ]

    operations = [
        migrations.RunPython(configure_workflow, migrations.RunPython.noop),
    ]
