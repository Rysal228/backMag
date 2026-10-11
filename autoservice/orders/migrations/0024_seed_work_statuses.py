from django.db import migrations


WORK_STATUSES = (
    ('waiting_manager_review', 'Ожидание проверки менеджером', 'warning'),
    ('manager_review', 'Проверяется менеджером', 'warning'),
    ('waiting_arrival', 'Ожидание прибытия авто в сервис', 'warning'),
    ('intake', 'Приёмка', 'warning'),
    ('owner_approval', 'Согласование с владельцем', 'warning'),
    ('waiting_payment', 'Ожидание оплаты', 'warning'),
    ('execution', 'Специалисты выполняют заказ', 'positive'),
    ('owner_visit', 'Владелец должен явиться в сервис', 'positive'),
    ('refused', 'Отказано', 'negative'),
)

WORK_TRANSITIONS = (
    ('waiting_manager_review', 'manager_review'),
    ('waiting_arrival', 'intake'),
    ('intake', 'owner_approval'),
    ('owner_approval', 'waiting_payment'),
    ('waiting_payment', 'execution'),
)


def configure_work_statuses(apps, schema_editor):
    WorkStatus = apps.get_model('orders', 'WorkStatus')
    WorkStatusTransition = apps.get_model('orders', 'WorkStatusTransition')

    statuses = {}
    for code, name, appearance in WORK_STATUSES:
        status = WorkStatus.objects.filter(code=code).first()
        if status is None:
            status = WorkStatus.objects.filter(name=name).first()

        if status is None:
            status = WorkStatus.objects.create(
                code=code,
                name=name,
                appearance=appearance,
            )
        else:
            status.code = code
            status.name = name
            status.appearance = appearance
            status.save(update_fields=('code', 'name', 'appearance'))

        statuses[code] = status

    WorkStatusTransition.objects.filter(role='admin').delete()

    for source, target in WORK_TRANSITIONS:
        WorkStatusTransition.objects.create(
            from_status=statuses[source],
            to_status=statuses[target],
            role='admin',
            enabled=True,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0023_rebuild_workflow_transitions'),
    ]

    operations = [
        migrations.RunPython(configure_work_statuses, migrations.RunPython.noop),
    ]
