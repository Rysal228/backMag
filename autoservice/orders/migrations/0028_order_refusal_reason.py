from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('orders', '0027_remove_status_appearance'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='refusal_reason',
            field=models.TextField(blank=True, default=''),
        ),
    ]
