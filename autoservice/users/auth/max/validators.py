import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.parse import parse_qsl

from django.conf import settings
from rest_framework.exceptions import AuthenticationFailed


MAX_INIT_DATA_MAX_AGE = 60 * 60
MAX_CONTACT_MAX_AGE = 5 * 60


@dataclass(frozen=True)
class ValidatedMaxInitData:
    user_id: int
    first_name: str
    last_name: str
    username: str | None
    auth_date: int
    hash: str


class MaxInitDataValidator:
    @classmethod
    def validate(
            cls,
            init_data: str,
    ) -> ValidatedMaxInitData:
        params = cls._parse(init_data)

        cls._validate_hash(params)

        auth_date = cls._validate_auth_date(params)

        user = cls._get_user(params)

        return ValidatedMaxInitData(
            user_id=user['id'],
            first_name=user.get('first_name', ''),
            last_name=user.get('last_name', ''),
            username=user.get('username'),
            auth_date=auth_date,
            hash=params['hash'],
        )

    @staticmethod
    def _parse(init_data: str) -> dict[str, str]:
        pairs = parse_qsl(
            init_data,
            keep_blank_values=True,
        )

        if not pairs:
            raise AuthenticationFailed(
                'MAX initData is empty.',
            )

        keys = [key for key, _ in pairs]

        if len(keys) != len(set(keys)):
            raise AuthenticationFailed(
                'MAX initData contains duplicate parameters.',
            )

        return dict(pairs)

    @classmethod
    def _validate_hash(
        cls,
        params: dict[str, str],
    ) -> None:
        received_hash = params.get('hash')

        if not received_hash:
            raise AuthenticationFailed(
                'MAX initData hash is missing.',
            )

        data_check_string = '\n'.join(
            f'{key}={value}'
            for key, value in sorted(params.items())
            if key != 'hash'
        )

        secret_key = hmac.new(
            key=b'WebAppData',
            msg=settings.MAX_BOT_TOKEN.encode(),
            digestmod=hashlib.sha256,
        ).digest()

        calculated_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode(),
            digestmod=hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(
            calculated_hash,
            received_hash,
        ):
            raise AuthenticationFailed(
                'Invalid MAX initData signature.',
            )

    @staticmethod
    def _validate_auth_date(
        params: dict[str, str],
    ) -> int:
        try:
            auth_date = int(params['auth_date'])
        except (KeyError, ValueError):
            raise AuthenticationFailed(
                'Invalid MAX auth_date.',
            )

        now = int(time.time())

        if auth_date > now:
            raise AuthenticationFailed(
                'MAX auth_date is in the future.',
            )

        if now - auth_date > MAX_INIT_DATA_MAX_AGE:
            raise AuthenticationFailed(
                'MAX initData has expired.',
            )

        return auth_date

    @staticmethod
    def _get_user(
        params: dict[str, str],
    ) -> dict:
        try:
            user = json.loads(params['user'])
        except (KeyError, json.JSONDecodeError):
            raise AuthenticationFailed(
                'Invalid MAX user data.',
            )

        user_id = user.get('id')

        if not isinstance(user_id, int):
            raise AuthenticationFailed(
                'Invalid MAX user id.',
            )

        return user


class MaxContactValidator:
    @staticmethod
    def validate(
        *,
        phone: str,
        auth_date: str,
        received_hash: str,
        user_id: int,
    ) -> None:
        normalized_phone = phone.removeprefix('+')

        MaxContactValidator._validate_auth_date(auth_date)

        data_check_string = (
            f'authDate={auth_date}\n'
            f'phone={normalized_phone}\n'
            f'userId={user_id}'
        )

        calculated_hash = hmac.new(
            key=settings.MAX_BOT_TOKEN.encode(),
            msg=data_check_string.encode(),
            digestmod=hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(
            calculated_hash,
            received_hash,
        ):
            raise AuthenticationFailed(
                'Invalid MAX phone signature.',
            )

    @staticmethod
    def _validate_auth_date(auth_date: str) -> None:
        try:
            timestamp = int(auth_date)
        except (TypeError, ValueError):
            raise AuthenticationFailed(
                'Invalid MAX phone auth_date.',
            )

        now = int(time.time())

        if timestamp > now:
            raise AuthenticationFailed(
                'MAX phone auth_date is in the future.',
            )

        if now - timestamp > MAX_CONTACT_MAX_AGE:
            raise AuthenticationFailed(
                'MAX phone verification has expired.',
            )