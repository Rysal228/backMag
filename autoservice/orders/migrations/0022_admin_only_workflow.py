from django.db import migrations


def remove_mechanic_workflow_transitions(apps, schema_editor):
    OrderStatusTransition = apps.get_model('orders', 'OrderStatusTransition')
    WorkStatusTransition = apps.get_model('orders', 'WorkStatusTransition')

    OrderStatusTransition.objects.filter(role='mechanic').delete()
    WorkStatusTransition.objects.filter(role='mechanic').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0021_configure_workflow'),
    ]

    operations = [
        migrations.RunPython(
            remove_mechanic_workflow_transitions,
            migrations.RunPython.noop,
        ),
    ]
