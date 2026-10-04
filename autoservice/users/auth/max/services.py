import secrets
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password, make_password
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import (
    APIException,
    AuthenticationFailed,
    Throttled,
)

from ...models import MaxAuthCode
from ..services import PhoneNormalizer
from ..tokens import create_auth_tokens
from .client import MaxBotApiError, MaxBotClient
from .validators import (
    MaxContactValidator,
    MaxInitDataValidator,
)


User = get_user_model()

MAX_CODE_TTL = timedelta(minutes=5)
MAX_CODE_RESEND_INTERVAL = timedelta(seconds=60)
MAX_CODE_MAX_ATTEMPTS = 5


class MaxAccountConflict(APIException):
    status_code = 409
    default_code = 'max_account_conflict'
    default_detail = (
        'Этот номер телефона или аккаунт MAX уже связан '
        'с другой учётной записью.'
    )


class MaxCodeDeliveryError(APIException):
    status_code = 502
    default_code = 'max_code_delivery_failed'
    default_detail = 'Не удалось отправить код в MAX.'


class MaxAuthService:

    @staticmethod
    @transaction.atomic
    def authenticate(
        *,
        init_data: str,
        phone: str | None = None,
        phone_auth_date: str | None = None,
        phone_hash: str | None = None,
    ) -> dict[str, str]:
        max_data = MaxInitDataValidator.validate(init_data)
        max_user_id = str(max_data.user_id)

        max_user = (
            User.objects
            .select_for_update()
            .filter(messenger_user_id=max_user_id)
            .first()
        )

        # Existing MAX account: no phone permission is needed again.
        if max_user is not None:
            if not max_user.is_active:
                raise AuthenticationFailed('User is inactive.')

            if phone is None:
                return create_auth_tokens(max_user)

            normalized_phone = PhoneNormalizer.normalize(phone)
            MaxContactValidator.validate(
                phone=normalized_phone,
                auth_date=phone_auth_date,
                received_hash=phone_hash,
                user_id=max_data.user_id,
            )
            if max_user.phone != normalized_phone:
                raise MaxAccountConflict()
            return create_auth_tokens(max_user)

        if phone is None:
            return {'status': 'contact_required'}

        phone = PhoneNormalizer.normalize(phone)
        MaxContactValidator.validate(
            phone=phone,
            auth_date=phone_auth_date,
            received_hash=phone_hash,
            user_id=max_data.user_id,
        )

        user = (
            User.objects
            .select_for_update()
            .filter(phone=phone)
            .first()
        )

        if user is None:
            user = MaxAuthService._create_user(
                phone=phone,
                messenger_user_id=max_user_id,
                first_name=max_data.first_name,
                last_name=max_data.last_name,
                username=max_data.username,
            )
        else:
            MaxAuthService._bind_max_account(
                user=user,
                messenger_user_id=max_user_id,
                first_name=max_data.first_name,
                last_name=max_data.last_name,
                username=max_data.username,
            )

        if not user.is_active:
            raise AuthenticationFailed('User is inactive.')

        return create_auth_tokens(user)

    @staticmethod
    @transaction.atomic
    def request_code(*, phone: str) -> None:
        phone = PhoneNormalizer.normalize(phone)

        user = (
            User.objects
            .select_for_update()
            .filter(phone=phone)
            .first()
        )

        if user is None or not user.is_active:
            raise AuthenticationFailed(
                'Не удалось отправить код для указанного номера телефона.'
            )

        if not user.messenger_user_id:
            raise AuthenticationFailed(
                'Для этого пользователя не настроена авторизация через MAX.'
            )

        now = timezone.now()
        previous_code = (
            MaxAuthCode.objects
            .filter(user=user)
            .order_by('-created_at')
            .first()
        )

        if (
            previous_code is not None
            and now - previous_code.created_at < MAX_CODE_RESEND_INTERVAL
        ):
            raise Throttled(
                detail='Повторно запросить код можно через 60 секунд.'
            )

        code = f'{secrets.randbelow(1_000_000):06d}'
        auth_code = MaxAuthCode.objects.create(
            user=user,
            code_hash=make_password(code),
            expires_at=now + MAX_CODE_TTL,
        )

        try:
            MaxBotClient().send_message_to_user(
                user_id=user.messenger_user_id,
                text=(
                    'Код для входа в автосервис: '
                    f'{code}\n\n'
                    'Код действует 5 минут. Никому его не сообщайте.'
                ),
            )
        except MaxBotApiError as exc:
            auth_code.delete()
            raise MaxCodeDeliveryError() from exc

    @staticmethod
    @transaction.atomic
    def verify_code(*, phone: str, code: str) -> dict[str, str]:
        phone = PhoneNormalizer.normalize(phone)
        user = (
            User.objects
            .select_for_update()
            .filter(phone=phone)
            .first()
        )

        if user is None or not user.is_active:
            raise AuthenticationFailed(
                'Неверный номер телефона или код.'
            )

        auth_code = (
            MaxAuthCode.objects
            .select_for_update()
            .filter(user=user)
            .order_by('-created_at')
            .first()
        )

        if auth_code is None:
            raise AuthenticationFailed(
                'Неверный номер телефона или код.'
            )

        if auth_code.used_at is not None:
            raise AuthenticationFailed(
                'Код уже использован.'
            )

        if timezone.now() >= auth_code.expires_at:
            raise AuthenticationFailed(
                'Срок действия кода истёк.'
            )

        if auth_code.attempts >= MAX_CODE_MAX_ATTEMPTS:
            raise AuthenticationFailed(
                'Превышено количество попыток ввода кода.'
            )

        if not check_password(code, auth_code.code_hash):
            auth_code.attempts += 1
            auth_code.save(update_fields=['attempts'])

            raise AuthenticationFailed(
                'Неверный номер телефона или код.'
            )

        auth_code.used_at = timezone.now()
        auth_code.save(update_fields=['used_at'])

        return create_auth_tokens(user)

    @staticmethod
    def _create_user(
            *,
            phone: str,
            messenger_user_id: str,
            first_name: str,
            last_name: str,
            username: str | None,
    ):
        return User.objects.create_user(
            phone=phone,
            password=None,
            messenger_user_id=messenger_user_id,
            first_name=first_name,
            last_name=last_name,
            username=username,
        )

    @staticmethod
    def _bind_max_account(
            *,
            user,
            messenger_user_id: str,
            first_name: str,
            last_name: str,
            username: str | None,
    ) -> None:
        current_max_id = user.messenger_user_id

        if current_max_id and current_max_id != messenger_user_id:
            raise MaxAccountConflict()

        update_fields = []

        if not current_max_id:
            user.messenger_user_id = messenger_user_id
            update_fields.append('messenger_user_id')

        if not user.first_name:
            user.first_name = first_name
            update_fields.append('first_name')

        if not user.last_name:
            user.last_name = last_name
            update_fields.append('last_name')

        if user.username is None and username:
            user.username = username
            update_fields.append('username')

        if update_fields:
            user.save(update_fields=update_fields)
