from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0018_order_work'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='order',
            name='work_type',
        ),
        migrations.RemoveField(
            model_name='order',
            name='work_types',
        ),
    ]
