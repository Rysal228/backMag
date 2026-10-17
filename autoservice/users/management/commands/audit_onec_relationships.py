"""Read-only coverage check for native 1C IDs on all legacy user relationships."""

from django.apps import apps
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Count all legacy user links and fail if any lacks a native 1C ID."

    def handle(self, *args, **options):
        User = get_user_model()
        total_users = User.objects.count()
        missing_users = User.objects.filter(onec_id__isnull=True).count()
        rows = [
            ("cars.Car.owner", apps.get_model("cars", "Car"), "owner", False),
            ("cars.CarOwnership.owner", apps.get_model("cars", "CarOwnership"), "owner", False),
            ("orders.Order.customer", apps.get_model("orders", "Order"), "customer", False),
            ("chats.ChatRoom.mechanic", apps.get_model("chats", "ChatRoom"), "mechanic", True),
            ("chats.ChatMessage.sender", apps.get_model("chats", "ChatMessage"), "sender", False),
            ("users.UserRoleAssignment.user", apps.get_model("users", "UserRoleAssignment"), "user", False),
            ("users.MaxAuthCode.user", apps.get_model("users", "MaxAuthCode"), "user", False),
        ]
        through = apps.get_model("orders", "Order").mechanics.through
        target = next(
            field.name for field in through._meta.fields
            if field.is_relation and field.related_model == User
        )
        rows.append(("orders.Order.mechanics", through, target, False))
        missing_any = missing_users > 0

        self.stdout.write(f"users.CustomUser: total={total_users}, no_onec_id={missing_users}")
        for label, model, field, nullable in rows:
            records = model.objects.all()
            if nullable:
                records = records.filter(**{f"{field}__isnull": False})
            total = records.count()
            missing = records.filter(
                **{f"{field}__onec_id__isnull": True}
            ).count()
            self.stdout.write(f"{label}: total_links={total}, no_onec_id={missing}")
            missing_any = missing_any or missing > 0

        attachments = apps.get_model("chats", "ChatAttachment").objects.count()
        self.stdout.write(
            f"chats.ChatAttachment: total={attachments} "
            "(linked to ChatMessage; no direct user FK)"
        )

        if total_users == 0 or missing_any:
            raise CommandError(
                "Some existing links have no verified native 1C identifier. "
                "Do not migrate ForeignKeys or JWT."
            )
        self.stdout.write(self.style.SUCCESS(
            "Coverage OK: all existing Django user links resolve to a native 1C UUID."
        ))
