"""Remove expired native-user refresh-token tombstones."""
from django.core.management.base import BaseCommand
from django.utils import timezone

from users.models import RevokedRefreshToken


class Command(BaseCommand):
    help = "Delete expired refresh-token revocations from PostgreSQL."

    def handle(self, *args, **options):
        deleted, _ = RevokedRefreshToken.objects.filter(
            expires_at__lte=timezone.now()
        ).delete()
        self.stdout.write(self.style.SUCCESS(f"Expired revocations removed: {deleted}"))
