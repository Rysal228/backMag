"""Site JWT tokens use 1C UUIDs and never depend on Django auth.User."""
from datetime import datetime, timezone as dt_timezone
from uuid import UUID

from django.db import transaction
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from integrations.services.onec_users import OneCUsersClient, OneCUserServiceError
from users.models import RevokedRefreshToken
from users.roles import resolve_active_role

from .identity import user_from_profile


SESSION_INVALID = 'Сессия устарела. Войдите в систему заново.'


def _new_refresh(user, *, active_role, auth_method, messenger_user_id='', max_verified_phone=''):
    token = RefreshToken()
    token['user_id'] = str(user.id)
    token['auth_method'] = auth_method
    token['active_role'] = resolve_active_role(user, active_role)
    if auth_method == 'max':
        if not messenger_user_id or not max_verified_phone:
            raise AuthenticationFailed('MAX-сессия больше не действительна.')
        token['messenger_user_id'] = messenger_user_id
        token['max_verified_phone'] = max_verified_phone
    return token


def _token_pair(token):
    return {
        'accessToken': str(token.access_token),
        'refreshToken': str(token),
    }


def create_auth_tokens(user, *, active_role=None):
    return _token_pair(_new_refresh(
        user, active_role=active_role, auth_method='password',
    ))


def create_max_auth_tokens(
    user, *, messenger_user_id, max_verified_phone, active_role=None,
):
    if (
        not messenger_user_id or not max_verified_phone
        or messenger_user_id != user.messenger_user_id
        or max_verified_phone != user.phone
    ):
        raise AuthenticationFailed('MAX-сессия больше не действительна.')
    return _token_pair(_new_refresh(
        user, active_role=active_role, auth_method='max',
        messenger_user_id=messenger_user_id,
        max_verified_phone=max_verified_phone,
    ))


def validate_token_subject(token):
    """Check the JWT identity, active role and MAX binding against current 1C."""
    try:
        onec_id = str(UUID(str(token['user_id'])))
    except (KeyError, ValueError, TypeError, AttributeError) as exc:
        raise AuthenticationFailed(SESSION_INVALID) from exc

    try:
        profile = OneCUsersClient().get_user_by_onec_id(onec_id)
    except OneCUserServiceError as exc:
        if exc.status_code == 404:
            raise AuthenticationFailed(SESSION_INVALID) from exc
        raise

    user = user_from_profile(profile)
    role = token.get('active_role')
    method = token.get('auth_method')
    if role not in user.roles or method not in ('password', 'max'):
        raise AuthenticationFailed(SESSION_INVALID)

    if method == 'max':
        messenger = token.get('messenger_user_id')
        verified_phone = token.get('max_verified_phone')
        if (
            not messenger
            or not verified_phone
            or messenger != user.messenger_user_id
            or verified_phone != user.phone
        ):
            raise AuthenticationFailed('MAX-сессия больше не действительна.')
    return user


def _parse_refresh(raw):
    try:
        token = RefreshToken(raw)
        jti = UUID(str(token['jti']))
        expiration = datetime.fromtimestamp(int(token['exp']), tz=dt_timezone.utc)
    except (TokenError, ValueError, TypeError, KeyError, OverflowError) as exc:
        raise AuthenticationFailed('Недействительный refresh-токен.') from exc
    return token, jti, expiration


def _revoke_jti(jti, expiration, *, allow_existing):
    _, created = RevokedRefreshToken.objects.get_or_create(
        jti=jti, defaults={'expires_at': expiration},
    )
    if not created and not allow_existing:
        raise AuthenticationFailed('Refresh-токен уже использован.')
    return created


def rotate_refresh_token(raw):
    token, jti, expiration = _parse_refresh(raw)
    user = validate_token_subject(token)
    role = token['active_role']
    method = token['auth_method']

    # Uniqueness of JTI makes concurrent refresh requests single-use.
    with transaction.atomic():
        _revoke_jti(jti, expiration, allow_existing=False)
        renewed = _new_refresh(
            user, active_role=role, auth_method=method,
            messenger_user_id=token.get('messenger_user_id', ''),
            max_verified_phone=token.get('max_verified_phone', ''),
        )
        return _token_pair(renewed)


def revoke_refresh_token(raw, *, user, access_token):
    token, jti, expiration = _parse_refresh(raw)
    if (
        str(token.get('user_id', '')) != str(user.id)
        or token.get('auth_method') != access_token.get('auth_method')
    ):
        raise AuthenticationFailed('Refresh-токен принадлежит другой сессии.')

    if token.get('auth_method') == 'max' and (
        token.get('messenger_user_id') != access_token.get('messenger_user_id')
        or token.get('max_verified_phone') != access_token.get('max_verified_phone')
    ):
        raise AuthenticationFailed('Refresh-токен принадлежит другой MAX-сессии.')

    # Idempotent: logging out an already used/rotated refresh is safe.
    with transaction.atomic():
        _revoke_jti(jti, expiration, allow_existing=True)
