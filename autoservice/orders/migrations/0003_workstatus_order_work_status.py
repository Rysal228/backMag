from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0002_order_appointment_at'),
    ]

    operations = [
        migrations.CreateModel(
            name='WorkStatus',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
            ],
            options={
                'verbose_name': 'Статус работы',
                'verbose_name_plural': 'Статусы работ',
            },
        ),
        migrations.AddField(
            model_name='order',
            name='work_status',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, to='orders.workstatus'),
        ),
    ]
