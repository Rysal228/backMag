from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0025_remove_order_price'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='orderstatus',
            name='appearance',
        ),
        migrations.RemoveField(
            model_name='workstatus',
            name='appearance',
        ),
        migrations.RemoveField(
            model_name='paymentstatus',
            name='appearance',
        ),
    ]
