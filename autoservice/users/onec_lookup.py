"""Resolve native 1C profiles for presentation without Django user relations."""

from integrations.services.onec_users import OneCUsersClient


def get_native_profile(user_id, context=None):
    if context is None:
        context = {}
    cache = context.setdefault("_onec_user_profiles", {})
    key = str(user_id)
    if key not in cache:
        cache[key] = OneCUsersClient().get_user_by_onec_id(key)
    return cache[key]


def native_display_name(profile):
    name = " ".join(
        part for part in (
            profile.get("lastName", ""), profile.get("firstName", ""),
            profile.get("patronymic", ""),
        ) if part
    ).strip()
    return name or profile.get("phone", "")
