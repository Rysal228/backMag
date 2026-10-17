"""Read-only audit of legacy Django UUID -> native 1C catalog reference UUID.

Run only after the live 1C HTTP response includes `onecId`.
This command neither migrates Django records nor writes to 1C.
"""

from uuid import UUID

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from integrations.services.onec_users import OneCUserServiceError, OneCUsersClient


class Command(BaseCommand):
    help = (
        "Compare legacy CustomUser UUIDs with the native reference UUIDs "
        "returned by 1C, without changing either database."
    )

    def add_arguments(self, parser):
        selection = parser.add_mutually_exclusive_group(required=True)
        selection.add_argument(
            "--all", action="store_true",
            help="Inspect every existing Django user; read-only.",
        )
        selection.add_argument(
            "--phone", action="append", default=None, dest="phones",
            help="Inspect one existing Django phone (repeat to select more).",
        )

    def handle(self, *args, **options):
        selected = None
        if not options["all"]:
            selected = {
                str(phone).strip().removeprefix("+")
                for phone in options["phones"]
            }
            if any(len(p) != 11 or not p.startswith("7") or not p.isascii()
                   or not p.isdigit() for p in selected):
                raise CommandError("Expected 11-digit phone: 7XXXXXXXXXX.")

        rows = get_user_model().objects.order_by("phone").values_list("pk", "phone")
        client = OneCUsersClient()
        processed = 0
        failed = 0
        observed_phones = set()
        native_to_legacy = {}

        for legacy_pk, django_phone in rows:
            normalized = str(django_phone).strip().removeprefix("+")
            if selected is not None and normalized not in selected:
                continue

            processed += 1
            observed_phones.add(normalized)
            try:
                response = client.get_user(normalized)
                native = str(UUID(str(response.get("onecId", ""))))
                legacy = str(UUID(str(response.get("externalId", ""))))
                expected_legacy = str(UUID(str(legacy_pk)))
                response_phone = str(response.get("phone", ""))
                if legacy != expected_legacy:
                    raise ValueError("externalId differs from Django UUID")
                if response_phone != normalized:
                    raise ValueError("phone differs between Django and 1C")
                other = native_to_legacy.get(native)
                if other is not None and other != legacy:
                    raise ValueError("native 1C ID is shared by multiple Django users")
                native_to_legacy[native] = legacy
            except (OneCUserServiceError, ValueError, TypeError) as exc:
                failed += 1
                self.stderr.write(
                    f"MISMATCH phone={normalized}: {type(exc).__name__}: {exc}"
                )
                continue

            self.stdout.write(
                f"OK phone={normalized} legacyDjangoId={legacy} onecId={native}"
            )

        if selected is not None:
            missing = selected - observed_phones
            for phone in sorted(missing):
                failed += 1
                self.stderr.write(f"MISSING Django user phone={phone}")

        self.stdout.write(
            f"Result: compared={processed}, ok={processed - (failed - (len(selected - observed_phones) if selected is not None else 0))}, errors={failed}"
        )
        if failed:
            raise CommandError(
                "Identity audit failed; do not rewrite any user IDs."
            )
        if processed == 0:
            raise CommandError(
                "No Django users audited. Identity mapping is not verified."
            )
