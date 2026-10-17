"""Safely bind existing Django users to the built-in 1C catalog UUIDs.

Default: read-only dry run. --apply is explicit and updates only CustomUser.onec_id.
Does not synchronize profiles, modify orders/chats/cars, or modify 1C.
"""

from uuid import UUID

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from integrations.services.onec_users import OneCUserServiceError, OneCUsersClient


def canonical_uuid(value, field, phone):
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise CommandError(
            f"Invalid {field} from 1C for phone={phone}; no changes made."
        ) from exc


def load_verified_mapping(rows, client):
    """Validate complete identity mapping before any write."""
    if not rows:
        raise CommandError("No users found in Django; no changes made.")

    result = {}
    reverse = {}
    for user in rows:
        phone = str(user.phone).strip().removeprefix("+")
        if len(phone) != 11 or not phone.startswith("7") or not phone.isascii() or not phone.isdigit():
            raise CommandError(f"Invalid Django phone for pk={user.pk}; no changes made.")
        try:
            remote = client.get_user(phone)
        except OneCUserServiceError as exc:
            raise CommandError(
                f"1C lookup failed for phone={phone}; no changes made: {exc}"
            ) from exc

        legacy_id = canonical_uuid(remote.get("externalId"), "externalId", phone)
        native_id = canonical_uuid(remote.get("onecId"), "onecId", phone)

        if str(remote.get("phone", "")) != phone or legacy_id != user.pk:
            raise CommandError(f"Identity mismatch for phone={phone}; no changes made.")

        previous_owner = reverse.get(native_id)
        if previous_owner is not None and previous_owner != user.pk:
            raise CommandError(
                f"Duplicate native 1C UUID for phone={phone}; no changes made."
            )
        reverse[native_id] = user.pk

        if user.onec_id is not None and user.onec_id != native_id:
            raise CommandError(
                f"Existing onec_id disagrees with 1C for phone={phone}; no changes made."
            )
        result[user.pk] = (phone, native_id)
    return result


class Command(BaseCommand):
    help = "Validate/bind Django user UUIDs to 1C native IDs (dry-run by default)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply", action="store_true",
            help="Write verified native IDs to nullable CustomUser.onec_id.",
        )

    def handle(self, *args, **options):
        User = get_user_model()
        # Read once and validate full population. These are identity keys only,
        # not a copy/synchronization of business profile fields.
        rows = list(User.objects.order_by("pk").only("pk", "phone", "onec_id"))
        mapping = load_verified_mapping(rows, OneCUsersClient())
        for user in rows:
            phone, native_id = mapping[user.pk]
            self.stdout.write(
                f"VERIFY phone={phone} legacyDjangoId={user.pk} onecId={native_id}"
            )

        if not options["apply"]:
            self.stdout.write(
                self.style.SUCCESS(
                    f"DRY RUN OK: {len(mapping)} users. No database writes. "
                    "Use --apply only after backup and review."
                )
            )
            return

        with transaction.atomic():
            locked = list(
                User.objects.select_for_update().order_by("pk").only(
                    "pk", "phone", "onec_id"
                )
            )
            # Refuse to apply a stale audit if registration or a local edit
            # occurred after the 1C lookup.
            if len(locked) != len(rows):
                raise CommandError("User count changed during audit; no changes made.")

            changes = []
            for user in locked:
                record = mapping.get(user.pk)
                if record is None:
                    raise CommandError("Django user set changed; no changes made.")
                phone, native_id = record
                if user.phone.strip().removeprefix("+") != phone:
                    raise CommandError(
                        f"Django phone changed for pk={user.pk}; no changes made."
                    )
                if user.onec_id not in (None, native_id):
                    raise CommandError(
                        f"onec_id changed for pk={user.pk}; no changes made."
                    )
                if user.onec_id is None:
                    user.onec_id = native_id
                    changes.append(user)

            if changes:
                User.objects.bulk_update(changes, ["onec_id"])

        self.stdout.write(
            self.style.SUCCESS(
                f"APPLIED: {len(mapping)} validated users, "
                f"{len(changes)} native IDs written. "
                "No other fields, tables or 1C records changed."
            )
        )
