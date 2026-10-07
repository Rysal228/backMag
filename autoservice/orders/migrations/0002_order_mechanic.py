from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0001_initial'),
        migrations.swappable_dependency('users.customuser'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='mechanic',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='assigned_orders',
                to='users.customuser',
                verbose_name='Специалист',
            ),
        ),
    ]
