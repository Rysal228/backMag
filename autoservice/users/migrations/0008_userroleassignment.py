from django.db import migrations, models


def copy_legacy_roles(apps, schema_editor):
    User = apps.get_model('users', 'CustomUser')
    UserRoleAssignment = apps.get_model('users', 'UserRoleAssignment')

    UserRoleAssignment.objects.bulk_create(
        [
            UserRoleAssignment(user=user, role=user.role)
            for user in User.objects.all().iterator()
        ],
        ignore_conflicts=True,
    )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0007_maxauthcode'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserRoleAssignment',
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
                    'role',
                    models.CharField(
                        choices=[
                            ('user', 'Пользователь'),
                            ('mechanic', 'Механик'),
                            ('admin', 'Администратор'),
                        ],
                        max_length=20,
                        verbose_name='Роль',
                    ),
                ),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=models.deletion.CASCADE,
                        related_name='role_assignments',
                        to='users.customuser',
                    ),
                ),
            ],
            options={
                'verbose_name': 'Роль пользователя',
                'verbose_name_plural': 'Роли пользователей',
                'constraints': [
                    models.UniqueConstraint(
                        fields=('user', 'role'),
                        name='unique_user_role',
                    ),
                ],
            },
        ),
        migrations.RunPython(copy_legacy_roles, noop),
        migrations.RemoveField(
            model_name='customuser',
            name='role',
        ),
    ]
