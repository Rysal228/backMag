from django.db import migrations, models


def create_default_filter_permissions(apps, schema_editor):
    OrderFilterPermission = apps.get_model('orders', 'OrderFilterPermission')

    filter_keys = [
        'search',
        'order_number',
        'vin',
        'plate_number',
        'brand',
        'model',
        'work_type',
        'status',
        'work_status',
        'date_range',
    ]

    defaults = {
        'user': {'search', 'order_number'},
        'mechanic': set(filter_keys),
        'admin': set(filter_keys),
    }

    for role, enabled_keys in defaults.items():
        OrderFilterPermission.objects.bulk_create(
            [
                OrderFilterPermission(
                    role=role,
                    filter_key=filter_key,
                    enabled=filter_key in enabled_keys,
                )
                for filter_key in filter_keys
            ]
        )


class Migration(migrations.Migration):
    dependencies = [
        ('orders', '0011_human_readable_order_numbers'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrderFilterPermission',
            fields=[
                (
                    'id',
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name='ID',
                    ),
                ),
                (
                    'role',
                    models.CharField(
                        choices=[
                            ('user', 'Пользователь'),
                            ('mechanic', 'Механик'),
                            ('admin', 'Администратор'),
                        ],
                        max_length=20,
                        verbose_name='Роль',
                    ),
                ),
                (
                    'filter_key',
                    models.CharField(
                        choices=[
                            ('search', 'Поиск'),
                            ('order_number', 'Номер заказа'),
                            ('vin', 'VIN'),
                            ('plate_number', 'Государственный номер'),
                            ('brand', 'Марка'),
                            ('model', 'Модель'),
                            ('work_type', 'Тип работ'),
                            ('status', 'Статус заказа'),
                            ('work_status', 'Статус работы'),
                            ('date_range', 'Период'),
                        ],
                        max_length=30,
                        verbose_name='Фильтр',
                    ),
                ),
                (
                    'enabled',
                    models.BooleanField(default=True, verbose_name='Разрешён'),
                ),
            ],
            options={
                'verbose_name': 'Доступ к фильтру заказа',
                'verbose_name_plural': 'Доступ к фильтрам заказов',
            },
        ),
        migrations.AddConstraint(
            model_name='orderfilterpermission',
            constraint=models.UniqueConstraint(
                fields=('role', 'filter_key'),
                name='unique_order_filter_permission',
            ),
        ),
        migrations.RunPython(create_default_filter_permissions, migrations.RunPython.noop),
    ]
