from django.db import migrations


def normalize_phone(phone: str) -> str:
    normalized = phone.strip()

    if normalized.startswith('+'):
        normalized = normalized[1:]

    if not normalized.isdigit():
        raise ValueError(
            f'Cannot normalize phone number: {phone!r}'
        )

    return normalized


def forwards(apps, schema_editor):
    User = apps.get_model('users', 'CustomUser')

    for user in User.objects.all().iterator():
        normalized_phone = normalize_phone(user.phone)

        if normalized_phone == user.phone:
            continue

        conflict = (
            User.objects
            .filter(phone=normalized_phone)
            .exclude(pk=user.pk)
            .exists()
        )

        if conflict:
            raise RuntimeError(
                'Phone normalization conflict: '
                f'{user.phone!r} -> {normalized_phone!r}'
            )

        User.objects.filter(pk=user.pk).update(
            phone=normalized_phone,
        )


def backwards(apps, schema_editor):
    # Phone numbers are intentionally stored without the leading '+'.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('users', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
