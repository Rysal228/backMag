from django.db import migrations, models


def set_initial_order_status(apps, schema_editor):
    OrderStatus = apps.get_model('orders', 'OrderStatus')
    OrderStatus.objects.filter(name='На рассмотрении').update(is_initial=True)


class Migration(migrations.Migration):
    dependencies = [
        ('orders', '0003_workstatus_order_work_status'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderstatus',
            name='appearance',
            field=models.CharField(
                choices=[
                    ('positive', 'Положительный'),
                    ('warning', 'Предупреждение'),
                    ('negative', 'Отрицательный'),
                ],
                default='warning',
                max_length=20,
                verbose_name='Внешний вид статуса',
            ),
        ),
        migrations.AddField(
            model_name='orderstatus',
            name='is_initial',
            field=models.BooleanField(default=False, verbose_name='Начальный статус'),
        ),
        migrations.AddField(
            model_name='workstatus',
            name='appearance',
            field=models.CharField(
                choices=[
                    ('positive', 'Положительный'),
                    ('warning', 'Предупреждение'),
                    ('negative', 'Отрицательный'),
                ],
                default='warning',
                max_length=20,
                verbose_name='Внешний вид статуса',
            ),
        ),
        migrations.RunPython(set_initial_order_status, migrations.RunPython.noop),
    ]
