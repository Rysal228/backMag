"""Native 1C UUID bridge tests; no database or network required."""

from contextlib import nullcontext
from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import UUID

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from users.management.commands.bind_onec_user_ids import load_verified_mapping


LEGACY = UUID("72e4ff86-8922-4e96-9087-500f4fb1f5bc")
NATIVE = UUID("37262ee6-c98a-11f1-9abc-fa163e59c328")
PHONE = "79135552525"


def user(*, legacy=LEGACY, phone=PHONE, onec_id=None):
    return SimpleNamespace(pk=legacy, phone=phone, onec_id=onec_id)


def profile(*, external_id=LEGACY, native_id=NATIVE, phone=PHONE):
    return {
        "externalId": str(external_id),
        "onecId": str(native_id),
        "phone": phone,
    }


class NativeIdBindingValidationTests(SimpleTestCase):
    def test_valid_map_uses_native_1c_reference(self):
        client = Mock()
        client.get_user.return_value = profile()
        self.assertEqual(load_verified_mapping([user()], client), {
            LEGACY: (PHONE, NATIVE)
        })

    def test_legacy_mismatch_rejects_all_writes(self):
        client = Mock()
        client.get_user.return_value = profile(
            external_id="44d93602-a058-4896-9f68-181bb34b4af3"
        )
        with self.assertRaises(CommandError):
            load_verified_mapping([user()], client)

    def test_existing_native_id_conflict_rejected(self):
        client = Mock()
        client.get_user.return_value = profile()
        with self.assertRaises(CommandError):
            load_verified_mapping([user(onec_id=UUID(int=1))], client)

    def test_duplicate_native_id_rejected(self):
        second = UUID("ccb58534-735a-471f-a7dd-0e87e70d6bcf")
        client = Mock()
        client.get_user.side_effect = [
            profile(),
            profile(external_id=second, phone="79135572795")
        ]
        with self.assertRaises(CommandError):
            load_verified_mapping([
                user(),
                user(legacy=second, phone="79135572795"),
            ], client)

    def test_missing_native_id_rejected(self):
        client = Mock()
        client.get_user.return_value = profile(native_id=None)
        with self.assertRaises(CommandError):
            load_verified_mapping([user()], client)

    def test_empty_users_rejected(self):
        with self.assertRaises(CommandError):
            load_verified_mapping([], Mock())


class NativeIdBindingCommandTests(SimpleTestCase):
    @patch("users.management.commands.bind_onec_user_ids.get_user_model")
    @patch("users.management.commands.bind_onec_user_ids.OneCUsersClient")
    def test_default_is_read_only(self, client_class, model_getter):
        users = model_getter.return_value.objects
        users.order_by.return_value.only.return_value = [user()]
        client_class.return_value.get_user.return_value = profile()
        out = StringIO()
        call_command("bind_onec_user_ids", stdout=out)
        self.assertIn("DRY RUN OK", out.getvalue())
        users.bulk_update.assert_not_called()
        users.select_for_update.assert_not_called()

    @patch("users.management.commands.bind_onec_user_ids.transaction.atomic")
    @patch("users.management.commands.bind_onec_user_ids.get_user_model")
    @patch("users.management.commands.bind_onec_user_ids.OneCUsersClient")
    def test_apply_is_idempotent_and_only_updates_native_ids(
        self, client_class, model_getter, atomic
    ):
        atomic.return_value = nullcontext()
        users = model_getter.return_value.objects
        users.order_by.return_value.only.return_value = [user()]
        users.select_for_update.return_value.order_by.return_value.only.return_value = [user()]
        client_class.return_value.get_user.return_value = profile()
        out = StringIO()
        call_command("bind_onec_user_ids", "--apply", stdout=out)
        self.assertIn("APPLIED:", out.getvalue())
        args = users.bulk_update.call_args.args
        self.assertEqual(args[0][0].onec_id, NATIVE)
        self.assertEqual(args[1], ["onec_id"])

    @patch("users.management.commands.bind_onec_user_ids.transaction.atomic")
    @patch("users.management.commands.bind_onec_user_ids.get_user_model")
    @patch("users.management.commands.bind_onec_user_ids.OneCUsersClient")
    def test_apply_blocks_changed_phone_before_write(
        self, client_class, model_getter, atomic
    ):
        atomic.return_value = nullcontext()
        users = model_getter.return_value.objects
        users.order_by.return_value.only.return_value = [user()]
        users.select_for_update.return_value.order_by.return_value.only.return_value = [
            user(phone="79999999999")
        ]
        client_class.return_value.get_user.return_value = profile()
        with self.assertRaises(CommandError):
            call_command("bind_onec_user_ids", "--apply", stdout=StringIO())
        users.bulk_update.assert_not_called()
