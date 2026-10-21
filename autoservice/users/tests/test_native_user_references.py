"""Native 1C user/order identifiers: no Django User or Order FK."""
from unittest.mock import patch
from uuid import UUID

from django.test import SimpleTestCase

from chats.models import ChatMessage, ChatRoom
from users.onec_lookup import get_native_profile, native_display_name


USER_ID = UUID("8996ef81-9116-4d75-a3de-2fa8a5bc6b10")


class NativeUserReferenceSchemaTests(SimpleTestCase):
    def test_chats_keep_only_native_uuids(self):
        for model, field in (
            (ChatRoom, "order_id"),
            (ChatRoom, "mechanic_id"),
            (ChatMessage, "sender_id"),
        ):
            with self.subTest(model=model.__name__):
                value = model._meta.get_field(field)
                self.assertEqual(value.get_internal_type(), "UUIDField")
                self.assertFalse(value.is_relation)

    @patch("users.onec_lookup.OneCUsersClient")
    def test_profile_lookup_is_cached_per_response(self, users):
        users.return_value.get_user_by_onec_id.return_value = {
            "onecId": str(USER_ID), "phone": "79135572795",
            "firstName": "Анна", "lastName": "Тестовая",
        }
        context = {}
        first = get_native_profile(USER_ID, context)
        self.assertIs(first, get_native_profile(USER_ID, context))
        self.assertEqual(native_display_name(first), "Тестовая Анна")
        users.return_value.get_user_by_onec_id.assert_called_once_with(str(USER_ID))
