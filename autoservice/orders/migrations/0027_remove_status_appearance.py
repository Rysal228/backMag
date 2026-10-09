from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0026_alter_orderstatustransition_role_and_more'),
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
