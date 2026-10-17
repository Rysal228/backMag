"""Gateway tests: profile reads/writes must not touch Django user fields."""

from types import SimpleNamespace
from unittest.mock import Mock, patch
import os
import uuid

import requests
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from integrations.services.onec_users import OneCUserServiceError, OneCUsersClient
from users.onec_profile_views import OneCProfileView


UUID = "44d93602-a058-4896-9f68-181bb34b4af3"
PHONE = "79999999999"


def remote_profile(**changes):
    data = {
        "externalId": UUID,
        "phone": PHONE,
        "firstName": "Имя из 1С",
        "lastName": "",
        "patronymic": "",
        "birthday": None,
        "roles": ["user"],
        "isActive": True,
    }
    data.update(changes)
    return data


class OneCProfileGatewayTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        # No database user object and no local profile cache are needed.
        self.user = SimpleNamespace(
            pk=uuid.UUID(UUID), phone=PHONE, is_authenticated=True
        )

    def call(self, method, payload=None):
        if method == "GET":
            req = self.factory.get("/api/v1/users/profile/")
        else:
            req = self.factory.patch(
                "/api/v1/users/profile/", payload, format="json"
            )
        force_authenticate(req, user=self.user, token={"active_role": "user"})
        req.active_role = "user"
        return OneCProfileView.as_view()(req)

    @patch("users.onec_profile_views.OneCUsersClient")
    def test_get_uses_only_onec_data(self, client_type):
        client_type.return_value.get_user.return_value = remote_profile()
        response = self.call("GET")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["firstName"], "Имя из 1С")
        self.assertEqual(response.data["user"]["id"], UUID)
        self.assertEqual(response.data["user"]["roles"], ["user"])
        client_type.return_value.get_user.assert_called_once_with(PHONE)
        client_type.return_value.patch_user.assert_not_called()

    @patch("users.onec_profile_views.OneCUsersClient")
    def test_patch_writes_only_to_onec_and_preserves_contract(self, client_type):
        client_type.return_value.get_user.return_value = remote_profile()
        client_type.return_value.patch_user.return_value = remote_profile(
            firstName="Новое имя"
        )
        response = self.call("PATCH", {"firstName": "Новое имя"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["firstName"], "Новое имя")
        client_type.return_value.patch_user.assert_called_once_with(
            PHONE, {"firstName": "Новое имя"}
        )

    @patch("users.onec_profile_views.OneCUsersClient")
    def test_patch_rejects_roles_and_phone(self, client_type):
        response = self.call("PATCH", {"roles": ["admin"], "phone": PHONE})
        self.assertEqual(response.status_code, 400)
        client_type.assert_not_called()

    @patch("users.onec_profile_views.OneCUsersClient")
    def test_rejects_mismatched_uuid(self, client_type):
        client_type.return_value.get_user.return_value = remote_profile(
            externalId="f5eb4394-a4b7-4a18-bd30-8e9b9ff34c80"
        )
        response = self.call("GET")
        self.assertEqual(response.status_code, 502)

    @patch("users.onec_profile_views.OneCUsersClient")
    def test_rejects_revoked_role(self, client_type):
        client_type.return_value.get_user.return_value = remote_profile(
            roles=["mechanic"]
        )
        response = self.call("GET")
        self.assertIn(response.status_code, (401, 403))

    @patch("users.onec_profile_views.OneCUsersClient")
    def test_blocks_updates_for_inactive_user(self, client_type):
        client_type.return_value.get_user.return_value = remote_profile(
            isActive=False
        )
        response = self.call("PATCH", {"firstName": "Вася"})
        self.assertIn(response.status_code, (401, 403))
        client_type.return_value.patch_user.assert_not_called()


class OneCUsersClientTests(SimpleTestCase):
    @patch.dict(os.environ, {
        "ONEC_BASE_URL": "http://host.docker.internal:8081",
        "ONEC_ALLOW_UNAUTHENTICATED_INTERNAL": "1",
        "ONEC_API_USER": "",
        "ONEC_API_PASSWORD": "",
    })
    @patch("integrations.services.onec_users.requests.request")
    def test_internal_client_reads_profile(self, request):
        request.return_value = Mock(
            ok=True, status_code=200, json=lambda: {"user": remote_profile()}
        )
        user = OneCUsersClient().get_user(PHONE)
        self.assertEqual(user["externalId"], UUID)
        self.assertEqual(request.call_args.args[0], "GET")
        self.assertTrue(request.call_args.kwargs["url"].endswith("/" + PHONE))
        self.assertFalse(request.call_args.kwargs["allow_redirects"])

    @patch.dict(os.environ, {
        "ONEC_BASE_URL": "http://example.org:8081",
        "ONEC_ALLOW_UNAUTHENTICATED_INTERNAL": "1",
        "ONEC_API_USER": "",
        "ONEC_API_PASSWORD": "",
    })
    def test_unauthenticated_access_forbids_noninternal_host(self):
        with self.assertRaises(OneCUserServiceError) as ctx:
            OneCUsersClient()
        self.assertEqual(ctx.exception.status_code, 503)

    @patch.dict(os.environ, {
        "ONEC_BASE_URL": "http://host.docker.internal:8081",
        "ONEC_ALLOW_UNAUTHENTICATED_INTERNAL": "1",
        "ONEC_API_USER": "",
        "ONEC_API_PASSWORD": "",
    })
    @patch("integrations.services.onec_users.requests.request")
    def test_service_timeout_returns_gateway_timeout(self, request):
        request.side_effect = requests.Timeout("timeout")
        with self.assertRaises(OneCUserServiceError) as ctx:
            OneCUsersClient().get_user(PHONE)
        self.assertEqual(ctx.exception.status_code, 504)
