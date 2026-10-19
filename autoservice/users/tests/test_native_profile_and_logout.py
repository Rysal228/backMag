"""Profile and logout endpoints work without PostgreSQL application users."""
from unittest.mock import patch
from uuid import UUID

from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate

from users.auth.identity import user_from_profile
from users.onec_profile_views import OneCProfileView
from users.views import LogoutView

ONEC_ID = "d2b65827-0e38-48b8-a27e-4aef3ce3c135"
PHONE = "79135572795"


def profile(**overrides):
    result = {
        "onecId": ONEC_ID,
        "phone": PHONE,
        "roles": ["user"],
        "isActive": True,
        "messengerUserId": "",
        "firstName": "Анна",
        "lastName": "Тестовая",
        "patronymic": "",
        "birthday": None,
        "hasPassword": True,
    }
    result.update(overrides)
    return result


class NativeProfileTests(SimpleTestCase):
    def setUp(self):
        self.user = user_from_profile(profile())
        self.factory = APIRequestFactory()

    def make_request(self, method, body=None):
        if method == "GET":
            request = self.factory.get("/api/v1/users/profile/")
        else:
            request = self.factory.patch(
                "/api/v1/users/profile/", body or {}, format="json",
            )
        force_authenticate(request, user=self.user, token={"active_role": "user"})
        request.active_role = "user"
        return request

    @patch("users.onec_profile_views.OneCUsersClient")
    def test_profile_id_is_onec_id(self, client):
        client.return_value.get_user.return_value = profile()
        response = OneCProfileView.as_view()(self.make_request("GET"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["id"], ONEC_ID)
        self.assertEqual(response.data["user"]["activeRole"], "user")

    @patch("users.onec_profile_views.OneCUsersClient")
    def test_patch_writes_only_to_onec(self, client):
        client.return_value.get_user.return_value = profile()
        client.return_value.patch_user.return_value = profile(firstName="Мария")
        response = OneCProfileView.as_view()(
            self.make_request("PATCH", {"firstName": "Мария"})
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["firstName"], "Мария")
        client.return_value.patch_user.assert_called_once_with(
            PHONE, {"firstName": "Мария"},
        )

    @patch("users.onec_profile_views.OneCUsersClient")
    def test_cannot_change_roles_in_profile_patch(self, client):
        response = OneCProfileView.as_view()(
            self.make_request("PATCH", {"roles": ["admin"]})
        )
        self.assertEqual(response.status_code, 400)
        client.return_value.patch_user.assert_not_called()

    @patch("users.onec_profile_views.OneCUsersClient")
    def test_uuid_mismatch_refuses_profile(self, client):
        client.return_value.get_user.return_value = profile(
            onecId="cccccccc-cccc-4ccc-8ccc-cccccccccccc"
        )
        response = OneCProfileView.as_view()(self.make_request("GET"))
        self.assertEqual(response.status_code, 502)


class NativeLogoutTests(SimpleTestCase):
    @patch("users.views.revoke_refresh_token")
    def test_logout_records_refresh_revocation(self, revoke):
        user = user_from_profile(profile())
        request = APIRequestFactory().post(
            "/api/v1/users/auth/logout/",
            {"refreshToken": "some.refresh.token"}, format="json",
        )
        token = {"active_role": "user", "auth_method": "password"}
        force_authenticate(request, user=user, token=token)
        request.active_role = "user"
        response = LogoutView.as_view()(request)
        self.assertEqual(response.status_code, 204)
        self.assertEqual(revoke.call_args.kwargs["user"].id, UUID(ONEC_ID))

    def test_logout_requires_refresh_token(self):
        request = APIRequestFactory().post(
            "/api/v1/users/auth/logout/", {}, format="json",
        )
        force_authenticate(
            request, user=user_from_profile(profile()),
            token={"active_role": "user", "auth_method": "password"},
        )
        response = LogoutView.as_view()(request)
        self.assertEqual(response.status_code, 400)
