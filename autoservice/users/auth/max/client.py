import requests
from django.conf import settings


class MaxBotApiError(Exception):
    """Raised when MAX Bot API rejects a request or is unavailable."""


class MaxBotClient:
    """Small client for server-to-server requests to the MAX Bot API."""

    def __init__(self, *, token: str | None = None, base_url: str | None = None):
        self.token = token or settings.MAX_BOT_TOKEN
        self.base_url = (
            base_url or settings.MAX_BOT_API_BASE_URL
        ).rstrip('/')

    def send_message_to_user(self, *, user_id: str, text: str) -> dict:
        response = requests.post(
            f'{self.base_url}/messages',
            params={'user_id': user_id},
            headers={
                'Authorization': self.token,
                'Content-Type': 'application/json',
            },
            json={'text': text},
            timeout=10,
        )

        if not response.ok:
            raise MaxBotApiError(
                f'MAX Bot API returned HTTP {response.status_code}: '
                f'{response.text}'
            )

        return response.json()
