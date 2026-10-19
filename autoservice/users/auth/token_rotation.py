"""Atomic refresh rotation without an application-user ORM table."""
from datetime import datetime, timezone

from django.db import IntegrityError, transaction
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from users.models import ConsumedRefreshToken
from users.authentication import validate_native_claims
from users.auth.tokens import TOKEN_VERSION


def parse_refresh(raw):
    try:
        return RefreshToken(raw)
    except (TokenError, TypeError, ValueError) as exc:
        raise AuthenticationFailed("Refresh-токен недействителен.") from exc


def consume_refresh(token):
    jti = token.get("jti")
    expires = token.get("exp")
    if not isinstance(jti, str) or not isinstance(expires, int):
        raise AuthenticationFailed("Refresh-токен недействителен.")
    try:
        with transaction.atomic():
            ConsumedRefreshToken.objects.create(
                jti=jti,
                expires_at=datetime.fromtimestamp(expires, timezone.utc),
            )
    except IntegrityError as exc:
        raise AuthenticationFailed("Refresh-токен уже использован.") from exc


def rotate_refresh(raw):
    previous = parse_refresh(raw)
    user, role = validate_native_claims(previous)
    method = previous["auth_method"]
    from users.auth.tokens import create_auth_tokens, create_max_auth_tokens

    # Locking unique JTI insert ensures only one parallel rotation succeeds.
    consume_refresh(previous)
    if method == "max":
        return create_max_auth_tokens(
            user, active_role=role,
            messenger_user_id=previous["messenger_user_id"],
            max_verified_phone=previous["max_verified_phone"],
        )
    return create_auth_tokens(user, active_role=role)


def logout_refresh(raw, current_user):
    previous = parse_refresh(raw)
    if previous.get("auth_version") != TOKEN_VERSION:
        raise ValidationError({"refreshToken": "Токен старой версии."})
    if previous.get("user_id") != str(current_user.pk):
        raise ValidationError({"refreshToken": "Токен другого пользователя."})
    consume_refresh(previous)
