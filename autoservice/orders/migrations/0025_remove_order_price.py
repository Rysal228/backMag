from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0024_seed_work_statuses'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='order',
            name='price',
        ),
    ]
