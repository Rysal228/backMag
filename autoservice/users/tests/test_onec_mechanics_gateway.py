"""Mechanic roster always comes from 1C; no Django ORM fallback."""

import os
import uuid
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from integrations.services.onec_users import OneCUserServiceError, OneCUsersClient
from users.views import CustomUserViewSet


PHONE = "79999999999"
USER_ID = "44d93602-a058-4896-9f68-181bb34b4af3"


def onec_profile():
    return {
        "externalId": USER_ID, "phone": PHONE, "firstName": "User",
        "lastName": "", "patronymic": "", "birthday": None,
        "isActive": True, "roles": ["user"],
    }


def mechanic():
    return {
        "id": "72e4ff86-8922-4e96-9087-500f4fb1f5bc",
        "phone": "79135552525",
        "firstName": "Имя из 1С",
        "lastName": "Фамилия", "patronymic": "", "birthday": None,
    }


class OneCMechanicsViewTests(SimpleTestCase):
    def setUp(self):
        self.user = SimpleNamespace(
            pk=uuid.UUID(USER_ID), phone=PHONE, is_authenticated=True
        )
        self.factory = APIRequestFactory()

    @patch("users.views.OneCUsersClient")
    def test_reads_mechanics_from_onec_not_django(self, client_type):
        client_type.return_value.get_user.return_value = onec_profile()
        client_type.return_value.list_mechanics.return_value = [mechanic()]
        request = self.factory.get(
            "/api/v1/users/",
            {"role": "mechanic", "search": "Имя", "ids": mechanic()["id"]},
        )
        force_authenticate(request, user=self.user, token={"active_role": "user"})
        request.active_role = "user"

        response = CustomUserViewSet.as_view({"get": "list"})(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]["firstName"], "Имя из 1С")
        client_type.return_value.get_user.assert_called_once_with(PHONE)
        client_type.return_value.list_mechanics.assert_called_once_with(
            search="Имя", ids=[mechanic()["id"]]
        )

    @patch("users.views.OneCUsersClient")
    def test_missing_auth_role_fails_closed(self, client_type):
        client_type.return_value.get_user.return_value = {
            **onec_profile(), "roles": ["mechanic"]
        }
        request = self.factory.get("/api/v1/users/", {"role": "mechanic", "search": "Тест"})
        force_authenticate(request, user=self.user, token={"active_role": "user"})
        request.active_role = "user"
        response = CustomUserViewSet.as_view({"get": "list"})(request)
        self.assertIn(response.status_code, (401, 403))
        client_type.return_value.list_mechanics.assert_not_called()


    @patch("users.views.OneCUsersClient")
    def test_1c_unavailable_never_falls_back_to_local_users(self, client_type):
        client_type.return_value.get_user.side_effect = OneCUserServiceError(
            "onec_unavailable", "Нет соединения с 1С."
        )
        request = self.factory.get("/api/v1/users/", {"role": "mechanic", "search": "Сер"})
        force_authenticate(request, user=self.user, token={"active_role": "user"})
        request.active_role = "user"
        response = CustomUserViewSet.as_view({"get": "list"})(request)
        self.assertEqual(response.status_code, 502)
        client_type.return_value.list_mechanics.assert_not_called()


class OneCMechanicsClientTests(SimpleTestCase):
    @patch.dict(os.environ, {
        "ONEC_BASE_URL": "http://host.docker.internal:8081",
        "ONEC_ALLOW_UNAUTHENTICATED_INTERNAL": "1",
        "ONEC_API_USER": "", "ONEC_API_PASSWORD": "",
    })
    @patch("integrations.services.onec_users.requests.request")
    def test_remote_filter_parameters(self, sender):
        sender.return_value = Mock(ok=True, status_code=200, json=lambda: [mechanic()])
        result = OneCUsersClient().list_mechanics(search="Имя", ids=[mechanic()["id"]])
        self.assertEqual(result, [mechanic()])
        self.assertEqual(sender.call_args.args[0], "GET")
        self.assertTrue(sender.call_args.args[1].endswith("/users/mechanics"))
        self.assertEqual(sender.call_args.kwargs["params"]["search"], "Имя")
        self.assertEqual(sender.call_args.kwargs["params"]["ids"], mechanic()["id"])

    @patch.dict(os.environ, {
        "ONEC_BASE_URL": "http://host.docker.internal:8081",
        "ONEC_ALLOW_UNAUTHENTICATED_INTERNAL": "1",
        "ONEC_API_USER": "", "ONEC_API_PASSWORD": "",
    })
    @patch("integrations.services.onec_users.requests.request")
    def test_invalid_1c_roster_is_rejected(self, sender):
        sender.return_value = Mock(ok=True, status_code=200, json=lambda: {"users": []})
        with self.assertRaises(OneCUserServiceError) as error:
            OneCUsersClient().list_mechanics(search="Тест")
        self.assertEqual(error.exception.status_code, 502)
