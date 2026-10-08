from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


def create_default_payment_statuses(apps, schema_editor):
    PaymentStatus = apps.get_model('orders', 'PaymentStatus')
    PaymentStatus.objects.get_or_create(
        code='unpaid',
        defaults={'name': 'Не оплачено', 'appearance': 'warning'},
    )
    PaymentStatus.objects.get_or_create(
        code='paid',
        defaults={'name': 'Оплачено', 'appearance': 'positive'},
    )


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0019_remove_order_legacy_work_types'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderstatus',
            name='code',
            field=models.CharField(blank=True, max_length=50, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='workstatus',
            name='code',
            field=models.CharField(blank=True, max_length=50, null=True, unique=True),
        ),
        migrations.CreateModel(
            name='PaymentStatus',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=50, unique=True)),
                ('name', models.CharField(max_length=100, unique=True)),
                ('appearance', models.CharField(choices=[('positive', 'Положительный'), ('warning', 'Предупреждение'), ('negative', 'Отрицательный')], default='warning', max_length=20)),
            ],
            options={
                'verbose_name': 'Статус оплаты',
                'verbose_name_plural': 'Статусы оплаты',
            },
        ),
        migrations.CreateModel(
            name='OrderStatusTransition',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('mechanic', 'Механик'), ('user', 'Пользователь'), ('admin', 'Администратор')], max_length=20)),
                ('enabled', models.BooleanField(default=True)),
                ('from_status', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='outgoing_transitions', to='orders.orderstatus')),
                ('to_status', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='incoming_transitions', to='orders.orderstatus')),
            ],
            options={
                'verbose_name': 'Переход статуса заказа',
                'verbose_name_plural': 'Переходы статусов заказа',
                'constraints': [models.UniqueConstraint(fields=('from_status', 'to_status', 'role'), name='unique_order_status_transition_role')],
            },
        ),
        migrations.CreateModel(
            name='WorkStatusTransition',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('mechanic', 'Механик'), ('user', 'Пользователь'), ('admin', 'Администратор')], max_length=20)),
                ('enabled', models.BooleanField(default=True)),
                ('from_status', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='outgoing_transitions', to='orders.workstatus')),
                ('to_status', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='incoming_transitions', to='orders.workstatus')),
            ],
            options={
                'verbose_name': 'Переход статуса работы',
                'verbose_name_plural': 'Переходы статусов работы',
                'constraints': [models.UniqueConstraint(fields=('from_status', 'to_status', 'role'), name='unique_work_status_transition_role')],
            },
        ),
        migrations.AddField(
            model_name='order',
            name='payment_status',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='orders', to='orders.paymentstatus'),
        ),
        migrations.AddConstraint(
            model_name='orderwork',
            constraint=models.UniqueConstraint(condition=Q(('work_type__isnull', False)), fields=('order', 'work_type'), name='unique_catalog_work_per_order'),
        ),
        migrations.RunPython(create_default_payment_statuses, migrations.RunPython.noop),
    ]
