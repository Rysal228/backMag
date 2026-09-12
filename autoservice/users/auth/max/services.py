from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.exceptions import AuthenticationFailed, APIException

from ..services import PhoneNormalizer
from ..tokens import create_auth_tokens
from .validators import (
    MaxContactValidator,
    MaxInitDataValidator,
)


User = get_user_model()


class MaxAccountConflict(APIException):
    status_code = 409
    default_code = 'max_account_conflict'
    default_detail = (
        'This phone number is already linked '
        'to another MAX account.'
    )


class MaxAuthService:

    @staticmethod
    @transaction.atomic
    def authenticate(
        *,
        init_data: str,
        phone: str,
        phone_auth_date: str,
        phone_hash: str,
    ) -> dict[str, str]:
        max_data = MaxInitDataValidator.validate(init_data)

        phone = PhoneNormalizer.normalize(phone)

        MaxContactValidator.validate(
            phone=phone,
            auth_date=phone_auth_date,
            received_hash=phone_hash,
            user_id=max_data.user_id,
        )

        max_user_id = str(max_data.user_id)

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
            raise AuthenticationFailed(
                'User is inactive.',
            )

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

        if current_max_id is not None and current_max_id != messenger_user_id:
            raise MaxAccountConflict()

        update_fields = []

        if current_max_id is None:
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