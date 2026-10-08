from django.db import migrations, models
import django.core.validators
import django.db.models.deletion


def migrate_work_types_to_order_works(apps, schema_editor):
    Order = apps.get_model('orders', 'Order')
    OrderWork = apps.get_model('orders', 'OrderWork')

    for order in Order.objects.prefetch_related('work_types').iterator():
        for work_type in order.work_types.all().order_by('id'):
            OrderWork.objects.create(
                order_id=order.pk,
                work_type_id=work_type.pk,
                name=work_type.name,
                price=0,
            )


class Migration(migrations.Migration):
    dependencies = [
        ('orders', '0017_remove_order_mechanic'),
    ]

    operations = [
        migrations.CreateModel(
            name='OrderWork',
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
                    'name',
                    models.CharField(
                        max_length=100,
                        verbose_name='Название работы',
                    ),
                ),
                (
                    'price',
                    models.DecimalField(
                        decimal_places=2,
                        default=0,
                        max_digits=12,
                        validators=[django.core.validators.MinValueValidator(0)],
                        verbose_name='Стоимость',
                    ),
                ),
                (
                    'order',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='works',
                        to='orders.order',
                        verbose_name='Заказ',
                    ),
                ),
                (
                    'work_type',
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name='order_works',
                        to='orders.worktype',
                        verbose_name='Тип работ из справочника',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Работа в заказе',
                'verbose_name_plural': 'Работы в заказах',
                'ordering': ('id',),
            },
        ),
        migrations.RunPython(
            migrate_work_types_to_order_works,
            migrations.RunPython.noop,
        ),
    ]
