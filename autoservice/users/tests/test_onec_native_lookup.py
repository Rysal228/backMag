"""Read-only 1C lookup by the native catalog reference ID."""

import os
from unittest.mock import Mock, patch
from uuid import UUID

from django.test import SimpleTestCase

from integrations.services.onec_users import OneCUserServiceError, OneCUsersClient


ONEC_ID = "37262ee6-c98a-11f1-9abc-fa163e59c328"
PHONE = "79135552525"
ROOT = "http://host.docker.internal:8081/ServiceCar/hs/api/user"


def profile(**overrides):
    user = {
        "onecId": ONEC_ID,
        "phone": PHONE,
        "firstName": "Сергей",
        "lastName": "Чер",
        "patronymic": "",
        "birthday": None,
        "isActive": True,
        "roles": ["user"],
    }
    user.update(overrides)
    return {"user": user}


@patch.dict(os.environ, {
    "ONEC_BASE_URL": "http://host.docker.internal:8081",
    "ONEC_ALLOW_UNAUTHENTICATED_INTERNAL": "1",
    "ONEC_API_USER": "",
    "ONEC_API_PASSWORD": "",
})
class OneCNativeUserLookupTests(SimpleTestCase):
    @patch("integrations.services.onec_users.requests.request")
    def test_reads_user_by_native_id(self, sender):
        sender.return_value = Mock(
            ok=True, status_code=200, json=lambda: profile()
        )
        result = OneCUsersClient().get_user_by_onec_id(UUID(ONEC_ID))
        self.assertEqual(result["onecId"], ONEC_ID)
        self.assertEqual(result["phone"], PHONE)
        self.assertEqual(sender.call_args.args, ("GET", ROOT + "/id/" + ONEC_ID))
        self.assertFalse(sender.call_args.kwargs["allow_redirects"])

    @patch("integrations.services.onec_users.requests.request")
    def test_invalid_uuid_fails_before_network(self, sender):
        with self.assertRaises(OneCUserServiceError) as failure:
            OneCUsersClient().get_user_by_onec_id("not-a-uuid")
        self.assertEqual(failure.exception.status_code, 400)
        sender.assert_not_called()

    @patch("integrations.services.onec_users.requests.request")
    def test_mismatched_native_id_fails_closed(self, sender):
        sender.return_value = Mock(
            ok=True, status_code=200,
            json=lambda: profile(onecId="5dd3df38-c986-11f1-9abc-fa163e59c328"),
        )
        with self.assertRaises(OneCUserServiceError) as failure:
            OneCUsersClient().get_user_by_onec_id(ONEC_ID)
        self.assertEqual(failure.exception.status_code, 502)

    @patch("integrations.services.onec_users.requests.request")
    def test_missing_native_id_fails_closed(self, sender):
        user = profile()
        del user["user"]["onecId"]
        sender.return_value = Mock(
            ok=True, status_code=200, json=lambda: user
        )
        with self.assertRaises(OneCUserServiceError) as failure:
            OneCUsersClient().get_user_by_onec_id(ONEC_ID)
        self.assertEqual(failure.exception.status_code, 502)

    @patch("integrations.services.onec_users.requests.request")
    def test_unknown_user_returns_404(self, sender):
        sender.return_value = Mock(
            ok=False, status_code=404,
            json=lambda: {"code": "user_not_found", "message": "Not found"},
        )
        with self.assertRaises(OneCUserServiceError) as failure:
            OneCUsersClient().get_user_by_onec_id(ONEC_ID)
        self.assertEqual(failure.exception.status_code, 404)

    @patch("integrations.services.onec_users.requests.request")
    def test_old_phone_profile_still_uses_original_route(self, sender):
        sender.return_value = Mock(
            ok=True, status_code=200, json=lambda: profile()
        )
        result = OneCUsersClient().get_user(PHONE)
        self.assertEqual(result["phone"], PHONE)
        self.assertEqual(sender.call_args.args, ("GET", ROOT + "/" + PHONE))
