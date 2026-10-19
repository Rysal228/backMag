"""Tests for 1C user UUID references in the PostgreSQL domain models."""
from types import SimpleNamespace
from unittest.mock import patch
from uuid import UUID

from django.test import SimpleTestCase
from rest_framework import serializers

from cars.models import Car, CarOwnership
from chats.models import ChatMessage, ChatRoom
from orders.models import Order, OrderMechanic
from orders.serializers import OrderSerializer
from users.onec_lookup import get_native_profile, native_display_name


USER_ID = UUID("8996ef81-9116-4d75-a3de-2fa8a5bc6b10")


class NativeUserReferenceSchemaTests(SimpleTestCase):
    def test_domain_models_store_only_native_uuid_not_user_fk(self):
        for model, field in (
            (Car, "owner_id"),
            (CarOwnership, "owner_id"),
            (Order, "customer_id"),
            (OrderMechanic, "mechanic_id"),
            (ChatRoom, "mechanic_id"),
            (ChatMessage, "sender_id"),
        ):
            with self.subTest(model=model.__name__):
                value = model._meta.get_field(field)
                self.assertEqual(value.get_internal_type(), "UUIDField")
                self.assertFalse(value.is_relation)

    def test_order_assignment_representation(self):
        assignments = SimpleNamespace(
            all=lambda: [SimpleNamespace(mechanic_id=USER_ID)],
        )
        self.assertEqual(
            Order.mechanic_ids.fget(SimpleNamespace(mechanic_links=assignments)),
            [USER_ID],
        )

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

    @patch("orders.serializers.OneCUsersClient")
    def test_non_mechanic_uuid_cannot_be_assigned(self, users):
        users.return_value.get_user_by_onec_id.return_value = {
            "onecId": str(USER_ID), "roles": ["user"], "isActive": True,
        }
        serializer = OrderSerializer()
        with self.assertRaises(serializers.ValidationError):
            serializer.validate_mechanics([USER_ID])

    def test_duplicate_mechanic_ids_cannot_be_assigned(self):
        serializer = OrderSerializer()
        with self.assertRaises(serializers.ValidationError):
            serializer.validate_mechanics([USER_ID, USER_ID])
