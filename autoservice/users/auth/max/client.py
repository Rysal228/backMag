import requests
from django.conf import settings


class MaxBotApiError(Exception):
    """На случай ошибок клиента"""


class MaxBotClient:

    def __init__(self, *, token: str | None = None, base_url: str | None = None):
        self.token = token or settings.MAX_BOT_TOKEN
        self.base_url = (
            base_url or settings.MAX_BOT_API_BASE_URL
        ).rstrip('/')

    def send_message_to_user(self, *, user_id: str, text: str) -> dict:
        try:
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
            response.raise_for_status()
        except requests.RequestException as exc:
            raise MaxBotApiError(
                f'MAX Bot API request failed: {exc}'
            ) from exc

        return response.json()
