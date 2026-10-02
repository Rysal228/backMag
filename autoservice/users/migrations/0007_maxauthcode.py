from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0006_merge_20260930_1958'),
    ]

    operations = [
        migrations.CreateModel(
            name='MaxAuthCode',
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
                    'code_hash',
                    models.CharField(max_length=128),
                ),
                (
                    'expires_at',
                    models.DateTimeField(),
                ),
                (
                    'attempts',
                    models.PositiveSmallIntegerField(default=0),
                ),
                (
                    'used_at',
                    models.DateTimeField(blank=True, null=True),
                ),
                (
                    'created_at',
                    models.DateTimeField(auto_now_add=True),
                ),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='max_auth_codes',
                        to='users.customuser',
                    ),
                ),
            ],
            options={
                'indexes': [
                    models.Index(
                        fields=['user', '-created_at'],
                        name='max_auth_code_user_created_idx',
                    ),
                ],
            },
        ),
    ]
