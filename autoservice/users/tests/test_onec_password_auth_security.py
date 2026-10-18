"""Security boundary tests for future 1C password verifier (no live network)."""

import os
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from integrations.services.onec_password_auth import OneCPasswordAuthClient
from integrations.services.onec_users import OneCUserServiceError


SECURE_ENV = {
    "ONEC_AUTH_VERIFY_URL": "https://auth.example.test/ServiceCarAuth/hs/auth/password/verify",
    "ONEC_AUTH_API_USER": "service-auth",
    "ONEC_AUTH_API_PASSWORD": "test-service-secret",
}
NATIVE = "37262ee6-c98a-11f1-9abc-fa163e59c328"
PHONE = "79135552525"


class OneCPasswordAuthSecurityTests(SimpleTestCase):
    @patch.dict(os.environ, {
        "ONEC_AUTH_VERIFY_URL": "http://host.docker.internal:8081/ServiceCar/hs/api",
        "ONEC_AUTH_API_USER": "service",
        "ONEC_AUTH_API_PASSWORD": "secret",
    })
    @patch("integrations.services.onec_password_auth.requests.post")
    def test_rejects_insecure_internal_http_even_with_credentials(self, post):
        with self.assertRaises(OneCUserServiceError) as caught:
            OneCPasswordAuthClient()
        self.assertEqual(caught.exception.status_code, 503)
        post.assert_not_called()

    @patch.dict(os.environ, {
        "ONEC_AUTH_VERIFY_URL": "",
        "ONEC_AUTH_API_USER": "",
        "ONEC_AUTH_API_PASSWORD": "",
    })
    @patch("integrations.services.onec_password_auth.requests.post")
    def test_default_internal_http_calls_existing_1c_endpoint(self, post):
        post.return_value = Mock(
            status_code=200, json=lambda: {
                "authenticated": True, "onecId": NATIVE, "phone": PHONE,
                "isActive": True, "roles": ["user"],
            }
        )
        identity = OneCPasswordAuthClient().verify_password(
            phone=PHONE, password="synthetic-password-for-test"
        )
        self.assertEqual(identity["onecId"], NATIVE)
        self.assertEqual(
            post.call_args.args[0],
            "http://host.docker.internal:8081/ServiceCar/hs/api/password/verify",
        )
        self.assertIsNone(post.call_args.kwargs["auth"])
        self.assertFalse(post.call_args.kwargs["allow_redirects"])

    @patch.dict(os.environ, {
        "ONEC_AUTH_VERIFY_URL": "http://host.docker.internal:8081/ServiceCar/hs/api/password/verify",
        "ONEC_AUTH_API_USER": "service",
        "ONEC_AUTH_API_PASSWORD": "secret",
    })
    @patch("integrations.services.onec_password_auth.requests.post")
    def test_internal_http_never_transmits_basic_secret(self, post):
        with self.assertRaises(OneCUserServiceError) as caught:
            OneCPasswordAuthClient()
        self.assertEqual(caught.exception.status_code, 503)
        post.assert_not_called()

    @patch.dict(os.environ, {
        "ONEC_AUTH_VERIFY_URL": "http://public.example.test/ServiceCar/hs/api/password/verify",
        "ONEC_AUTH_API_USER": "",
        "ONEC_AUTH_API_PASSWORD": "",
    })
    @patch("integrations.services.onec_password_auth.requests.post")
    def test_http_does_not_allow_arbitrary_destinations(self, post):
        with self.assertRaises(OneCUserServiceError) as caught:
            OneCPasswordAuthClient()
        self.assertEqual(caught.exception.status_code, 503)
        post.assert_not_called()

    @patch.dict(os.environ, SECURE_ENV | {
        "ONEC_AUTH_API_USER": "", "ONEC_AUTH_API_PASSWORD": "",
    })
    @patch("integrations.services.onec_password_auth.requests.post")
    def test_missing_service_auth_rejected(self, post):
        with self.assertRaises(OneCUserServiceError) as caught:
            OneCPasswordAuthClient()
        self.assertEqual(caught.exception.status_code, 503)
        post.assert_not_called()

    @patch.dict(os.environ, SECURE_ENV)
    @patch("integrations.services.onec_password_auth.requests.post")
    def test_success_requires_active_user_and_roles(self, post):
        post.return_value = Mock(
            status_code=200, json=lambda: {
                "authenticated": True, "onecId": NATIVE, "phone": PHONE,
                "isActive": True, "roles": ["mechanic", "user"],
            }
        )
        identity = OneCPasswordAuthClient().verify_password(
            phone=PHONE, password="secret-for-test"
        )
        self.assertEqual(identity, {
            "onecId": NATIVE, "phone": PHONE, "roles": ["mechanic", "user"],
        })
        kwargs = post.call_args.kwargs
        self.assertEqual(kwargs["json"]["password"], "secret-for-test")
        self.assertEqual(kwargs["auth"][0], "service-auth")
        self.assertEqual(kwargs["allow_redirects"], False)
        self.assertNotIn("verify", kwargs)

    @patch.dict(os.environ, SECURE_ENV)
    @patch("integrations.services.onec_password_auth.requests.post")
    def test_wrong_password_returns_no_identity(self, post):
        post.return_value = Mock(
            status_code=200, json=lambda: {"authenticated": False}
        )
        self.assertIsNone(
            OneCPasswordAuthClient().verify_password(
                phone=PHONE, password="incorrect"
            )
        )

    @patch.dict(os.environ, SECURE_ENV)
    @patch("integrations.services.onec_password_auth.requests.post")
    def test_deactivated_user_rejected(self, post):
        post.return_value = Mock(
            status_code=200, json=lambda: {
                "authenticated": True, "onecId": NATIVE, "phone": PHONE,
                "isActive": False, "roles": ["user"],
            }
        )
        with self.assertRaises(OneCUserServiceError) as caught:
            OneCPasswordAuthClient().verify_password(
                phone=PHONE, password="some-secret"
            )
        self.assertEqual(caught.exception.status_code, 502)

    @patch.dict(os.environ, SECURE_ENV)
    @patch("integrations.services.onec_password_auth.requests.post")
    def test_invalid_phone_does_not_send_password(self, post):
        with self.assertRaises(OneCUserServiceError):
            OneCPasswordAuthClient().verify_password(
                phone="bad-phone", password="secret"
            )
        post.assert_not_called()

    @patch.dict(os.environ, SECURE_ENV)
    @patch("integrations.services.onec_password_auth.requests.post")
    def test_service_auth_401_is_not_interpreted_as_user_password_error(self, post):
        post.return_value = Mock(status_code=401)
        with self.assertRaises(OneCUserServiceError) as caught:
            OneCPasswordAuthClient().verify_password(
                phone=PHONE, password="some-secret"
            )
        self.assertEqual(caught.exception.status_code, 502)

    @patch.dict(os.environ, SECURE_ENV)
    @patch("integrations.services.onec_password_auth.requests.post")
    def test_identity_mismatch_rejected(self, post):
        post.return_value = Mock(
            status_code=200, json=lambda: {
                "authenticated": True, "onecId": NATIVE,
                "phone": "79999999999", "isActive": True, "roles": ["user"],
            }
        )
        with self.assertRaises(OneCUserServiceError) as caught:
            OneCPasswordAuthClient().verify_password(
                phone=PHONE, password="some-secret"
            )
        self.assertEqual(caught.exception.status_code, 502)
