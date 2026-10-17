"""Mapping audit is read-only and refuses incomplete identity correspondence."""

from io import StringIO
from unittest.mock import Mock, patch
from uuid import UUID

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase


LEGACY = UUID("72e4ff86-8922-4e96-9087-500f4fb1f5bc")
NATIVE = UUID("d44950ce-9cae-46b0-880a-7bfa14b74b9f")
PHONE = "79135552525"
COMMAND_MODULE = "users.management.commands.audit_onec_user_ids"


def remote_identity(**overrides):
    user = {
        "onecId": str(NATIVE),
        "externalId": str(LEGACY),
        "phone": PHONE,
        "firstName": "Сергей",
        "lastName": "",
        "patronymic": "",
        "birthday": None,
        "isActive": True,
        "roles": ["user"],
    }
    user.update(overrides)
    return user


class OneCNativeIdentityAuditTests(SimpleTestCase):
    @patch(COMMAND_MODULE + ".OneCUsersClient")
    @patch(COMMAND_MODULE + ".get_user_model")
    def test_audit_reports_legacy_and_native_id_without_writing(
        self, user_model, client_type
    ):
        users = user_model.return_value.objects.order_by.return_value
        users.values_list.return_value = [(LEGACY, PHONE)]
        client_type.return_value.get_user.return_value = remote_identity()

        out = StringIO()
        call_command("audit_onec_user_ids", "--all", stdout=out)

        self.assertIn("legacyDjangoId=" + str(LEGACY), out.getvalue())
        self.assertIn("onecId=" + str(NATIVE), out.getvalue())
        self.assertIn("compared=1, ok=1, errors=0", out.getvalue())
        client_type.return_value.get_user.assert_called_once_with(PHONE)

    @patch(COMMAND_MODULE + ".OneCUsersClient")
    @patch(COMMAND_MODULE + ".get_user_model")
    def test_audit_fails_when_1c_does_not_expose_native_id(
        self, user_model, client_type
    ):
        user_model.return_value.objects.order_by.return_value.values_list.return_value = [
            (LEGACY, PHONE)
        ]
        user = remote_identity()
        del user["onecId"]
        client_type.return_value.get_user.return_value = user

        with self.assertRaises(CommandError):
            call_command(
                "audit_onec_user_ids", "--all",
                stdout=StringIO(), stderr=StringIO()
            )

    @patch(COMMAND_MODULE + ".OneCUsersClient")
    @patch(COMMAND_MODULE + ".get_user_model")
    def test_audit_fails_for_mismatched_legacy_id(
        self, user_model, client_type
    ):
        user_model.return_value.objects.order_by.return_value.values_list.return_value = [
            (LEGACY, PHONE)
        ]
        client_type.return_value.get_user.return_value = remote_identity(
            externalId="ee8cdfe4-4b2f-4bd4-a8a7-671e38a3d291"
        )
        with self.assertRaises(CommandError):
            call_command(
                "audit_onec_user_ids", "--all",
                stdout=StringIO(), stderr=StringIO()
            )

    @patch(COMMAND_MODULE + ".OneCUsersClient")
    @patch(COMMAND_MODULE + ".get_user_model")
    def test_audit_fails_for_duplicate_native_id(
        self, user_model, client_type
    ):
        other_legacy = UUID("44d93602-a058-4896-9f68-181bb34b4af3")
        other_phone = "79999999999"
        user_model.return_value.objects.order_by.return_value.values_list.return_value = [
            (LEGACY, PHONE), (other_legacy, other_phone)
        ]
        client_type.return_value.get_user.side_effect = [
            remote_identity(),
            remote_identity(externalId=str(other_legacy), phone=other_phone)
        ]
        with self.assertRaises(CommandError):
            call_command(
                "audit_onec_user_ids", "--all",
                stdout=StringIO(), stderr=StringIO()
            )

    @patch(COMMAND_MODULE + ".OneCUsersClient")
    @patch(COMMAND_MODULE + ".get_user_model")
    def test_phone_audit_fails_when_local_user_is_absent(
        self, user_model, client_type
    ):
        user_model.return_value.objects.order_by.return_value.values_list.return_value = []
        with self.assertRaises(CommandError):
            call_command(
                "audit_onec_user_ids", "--phone", PHONE,
                stdout=StringIO(), stderr=StringIO()
            )
        client_type.return_value.get_user.assert_not_called()
