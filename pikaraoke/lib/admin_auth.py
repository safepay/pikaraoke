"""Admin password storage and the server's cookie-signing key."""

import secrets

from pikaraoke.lib.password_hashing import hash_password, verify_password
from pikaraoke.lib.preference_manager import PreferenceManager

# Its own config.ini section, so it is never mistaken for something to hand-edit
# and never cleared by "reset all preferences".
_SECTION = "SECRETS"


class AdminAuth:
    """Owns whether an admin password is set, and verifies attempts against it."""

    def __init__(self, preferences: PreferenceManager) -> None:
        self._preferences = preferences
        if not self._get("secret_key"):
            self._set("secret_key", secrets.token_hex(32))

    @property
    def secret_key(self) -> str:
        """Flask's session-signing key, generated once and reused across restarts."""
        return self._get("secret_key")

    @property
    def session_token(self) -> str:
        """Identifies the current password, so changing it logs every device out."""
        return self._get("session_token")

    def is_password_set(self) -> bool:
        """True when admin mode is locked down. False means everyone is an admin."""
        return bool(self._get("password_hash"))

    def set_password(self, password: str | None) -> None:
        """Set the admin password, or clear it with None or an empty string."""
        self._set("password_hash", hash_password(password) if password else "")
        self._set("session_token", secrets.token_hex(16))

    def verify(self, password: str) -> bool:
        """True if the password matches the stored hash."""
        return verify_password(password, self._get("password_hash"))

    def _get(self, key: str) -> str:
        return self._preferences.get(key, "", section=_SECTION)

    def _set(self, key: str, value: str) -> None:
        self._preferences.set(key, value, section=_SECTION)
