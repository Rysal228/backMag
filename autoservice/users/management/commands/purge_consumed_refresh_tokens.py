"""Clean old refresh JTI revocations; safe to schedule once daily."""
from django.core.management.base import BaseCommand
from django.utils import timezone
from users.models import ConsumedRefreshToken


class Command(BaseCommand):
    help = "Удаляет использованные refresh JTI с истекшим сроком действия."

    def handle(self, *args, **options):
        total, _ = ConsumedRefreshToken.objects.filter(
            expires_at__lt=timezone.now(),
        ).delete()
        self.stdout.write(self.style.SUCCESS(f"Удалено записей: {total}"))
