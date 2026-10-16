import os
from urllib.parse import quote

import requests
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Import Django users and role assignments into 1C via idempotent HTTP PUT."

    def add_arguments(self, parser):
        parser.add_argument("--execute", action="store_true", help="Actually write to 1C; otherwise dry-run")
        parser.add_argument("--limit", type=int, default=None, help="Maximum number of users")
        parser.add_argument("--phone", help="Import just one user (7XXXXXXXXXX, optionally +)")
        parser.add_argument("--timeout", type=float, default=15.0, help="Seconds per HTTP request")
        parser.add_argument("--stop-on-error", action="store_true", help="Stop at the first error")

    def handle(self, *args, **options):
        base_url = os.environ.get("ONEC_BASE_URL", "http://host.docker.internal:8081").rstrip("/")
        service_path = os.environ.get("ONEC_USERS_PATH", "/ServiceCar/hs/api/user").strip("/")
        api_user = os.environ.get("ONEC_API_USER")
        api_password = os.environ.get("ONEC_API_PASSWORD")

        if options["limit"] is not None and options["limit"] <= 0:
            raise CommandError("--limit must be positive")
        if options["timeout"] <= 0:
            raise CommandError("--timeout must be positive")

        User = get_user_model()
        qs = User.objects.order_by("phone").prefetch_related("role_assignments")
        if options["phone"]:
            phone = options["phone"].strip().removeprefix("+")
            qs = qs.filter(phone=phone)
        if options["limit"] is not None:
            qs = qs[: options["limit"]]

        # Both staging and production use the exact same Django ORM data shape.
        users = list(qs)
        if not users:
            raise CommandError("No users found. Check filters/database.")

        if options["execute"] and (not api_user or not api_password):
            raise CommandError("Set ONEC_API_USER and ONEC_API_PASSWORD before --execute")

        session = requests.Session()
        if api_user and api_password:
            session.auth = (api_user, api_password)
        session.headers.update({"Accept": "application/json"})

        imported = 0
        failed = 0
        self.stdout.write(f"Mode: {'EXECUTE' if options['execute'] else 'DRY RUN'}; users: {len(users)}")

        for user in users:
            # The current Django DB stores phone in the normalized 7XXXXXXXXXX form.
            phone = user.phone.strip().removeprefix("+")
            roles = sorted({entry.role for entry in user.role_assignments.all()})
            if (len(phone) != 11 or not phone.isascii() or not phone.isdigit() or
                    not phone.startswith("7")):
                failed += 1
                self.stderr.write(f"INVALID PHONE for user id={user.pk}")
                if options["stop_on_error"]:
                    break
                continue
            if not roles or not set(roles).issubset({"user", "mechanic", "admin"}):
                failed += 1
                self.stderr.write(f"INVALID ROLES for phone={phone}: {roles}")
                if options["stop_on_error"]:
                    break
                continue

            first_name = user.first_name.strip()
            last_name = user.last_name.strip()
            patronymic = (user.patronymic or "").strip()
            messenger_id = user.messenger_user_id or ""
            if (not first_name or len(first_name) > 150 or
                    not last_name or len(last_name) > 150 or
                    len(patronymic) > 150 or len(messenger_id) > 255):
                failed += 1
                self.stderr.write(
                    f"INVALID PROFILE for phone={phone}: "
                    "1C requires non-empty first/last names (max 150 chars); "
                    "patronymic max 150; messengerUserId max 255."
                )
                if options["stop_on_error"]:
                    break
                continue

            payload = {
                "externalId": str(user.pk),
                "phone": phone,
                "firstName": first_name,
                "lastName": last_name,
                "patronymic": patronymic,
                "birthday": user.birthday.isoformat() if user.birthday else None,
                "messengerUserId": messenger_id,
                "isActive": bool(user.is_active),
                "roles": roles,
            }

            if not options["execute"]:
                self.stdout.write(f"DRY RUN phone={phone}, id={user.pk}, roles={','.join(roles)}")
                imported += 1
                continue

            url = f"{base_url}/{service_path}/{quote(phone, safe='')}"
            try:
                response = session.put(url, json=payload, timeout=options["timeout"])
                response.raise_for_status()
                body = response.json()
                if not isinstance(body, dict) or not isinstance(body.get("user"), dict):
                    raise ValueError("1C response must contain a user JSON object")
                remote = body["user"]
                if (remote.get("phone") != phone or
                        remote.get("externalId") != str(user.pk) or
                        remote.get("firstName") != first_name or
                        remote.get("lastName") != last_name or
                        remote.get("patronymic") != patronymic or
                        remote.get("birthday") != payload["birthday"] or
                        remote.get("messengerUserId") != messenger_id or
                        sorted(remote.get("roles", [])) != roles or
                        remote.get("isActive") != user.is_active):
                    raise ValueError("1C response differs from source user profile or roles")
            except (requests.RequestException, ValueError) as exc:
                failed += 1
                self.stderr.write(f"FAIL phone={phone}: {exc}")
                if options["stop_on_error"]:
                    break
                continue

            imported += 1
            self.stdout.write(f"OK phone={phone}")

        self.stdout.write(self.style.SUCCESS(f"Result: processed={imported + failed}, ok={imported}, failed={failed}"))
        if failed:
            raise CommandError("Import had errors; fix issues and re-run. PUT is idempotent.")
