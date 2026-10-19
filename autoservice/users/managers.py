"""Compatibility import for historical users.0002 migration only."""
from django.contrib.auth.models import UserManager


class CustomUserManager(UserManager):
    """Never used by the running application; historical migration reference."""
    pass
