"""Flask application context utilities for PiKaraoke."""

import logging
from typing import Any
from urllib.parse import unquote

from flask import current_app, g, request, session
from flask_socketio import emit

from pikaraoke.karaoke import Karaoke
from pikaraoke.lib.admin_auth import AdminAuth
from pikaraoke.lib.login_throttle import LoginThrottle


def current_singer_name() -> str | None:
    """The singer named by this device's cookie, or None when unnamed.

    js-cookie percent-encodes what it writes, so the stored value is decoded
    here; a blank or whitespace-only name counts as none. This is the server's
    one read of the identity cookie -- favourite stars are drawn from it.
    """
    raw = request.cookies.get("user")
    if not raw:
        return None
    return unquote(raw).strip() or None


def _session_singer_id(singers) -> int | None:
    """The logged-in singer id from the signed session, validated against `singers`."""
    singer_id = session.get("singer_id")
    if singer_id is None:
        return None
    token = singers.session_token(singer_id)
    if token is None or session.get("singer_token") != token:
        return None
    return singer_id


def current_singer_id() -> int | None:
    """The singer this device is logged in as, or None.

    An in-route check beside is_admin(), never the before_request gate. The signed
    session carries the singer id and a digest of their current secret_hash, so
    changing or clearing the password invalidates it.
    """
    return _session_singer_id(get_karaoke_instance().singer_manager)


def grant_singer_session(singer_id: int, token: str) -> None:
    """Log this device in as a singer until the password changes or the cookie expires."""
    session["singer_id"] = singer_id
    session["singer_token"] = token
    session.permanent = True


def clear_singer_session() -> None:
    """Forget any singer login on this device; the name cookie is the client's to clear."""
    session.pop("singer_id", None)
    session.pop("singer_token", None)


def authorized_singer_name() -> str | None:
    """This device's singer name, but only when it may touch that singer's saved data.

    An unprotected name is served on courtesy; a protected one needs this device
    logged in as it, or the caller to be the admin. None otherwise, so a read
    yields no stars and a write is refused.
    """
    name = current_singer_name()
    if name is None:
        return None
    singers = get_karaoke_instance().singer_manager
    if not singers.is_protected(name) or is_admin():
        return name
    singer = singers.find(name)
    return name if singer and current_singer_id() == singer["id"] else None


def singer_lock_barrier(k, name: str) -> str | None:
    """Why a named singer's write is barred on this device, or None when allowed.

    "locked": the name is protected and this device is not logged in as it.
    "unprotected": the require-a-password policy is on and the name has no lock yet.
    The admin always passes. Takes the Karaoke instance the caller already holds,
    so it honours a route's own lookup rather than reaching for the global.
    """
    singers = k.singer_manager
    if singers.is_protected(name):
        if is_admin():
            return None
        singer = singers.find(name)
        return None if singer and _session_singer_id(singers) == singer["id"] else "locked"
    if getattr(k, "require_singer_password", False):
        return None if is_admin() else "unprotected"
    return None


def favourite_paths() -> set[str]:
    """This device's singer's starred songs in the library, cached per request.

    A template global the song lists call per row, so it must cost one query a
    render. Empty for an unnamed device, or a protected one not logged in here, so
    those rows draw unfilled; clicking a star then asks for the name or password.
    """
    if "favourite_paths" not in g:
        name = authorized_singer_name()
        g.favourite_paths = (
            get_karaoke_instance().singer_manager.get_favourite_paths(name) if name else set()
        )
    return g.favourite_paths


def is_admin() -> bool:
    """Whether this request is authenticated as the admin.

    With no admin password set everyone is an admin -- the right default for a box
    on a home TV. Otherwise it takes a signed session established by /auth.
    """
    auth = get_admin_auth()
    return not auth.is_password_set() or session.get("admin") == auth.session_token


def get_karaoke_instance() -> Karaoke:
    """Get the current app's Karaoke instance
    This function returns the Karaoke instance stored in the current app's configuration.
    Returns:
        Karaoke: The Karaoke instance stored in the current app's configuration.
    """
    return current_app.config["KARAOKE_INSTANCE"]


def get_admin_auth() -> AdminAuth:
    """Get the current app's admin authentication store."""
    return current_app.config["ADMIN_AUTH"]


def get_login_throttle() -> LoginThrottle:
    """Get the current app's login brute-force throttle."""
    return current_app.config["LOGIN_THROTTLE"]


def get_site_name() -> str:
    """Get the site name from the current app's configuration
    This function returns the site name stored in the current app's configuration.
    Returns:
        str: The site name stored in the current app's configuration.
    """
    return current_app.config["SITE_NAME"]


def broadcast_event(event: str, data: Any = None) -> None:
    """Broadcast a SocketIO event to all connected clients.

    Args:
        event: Name of the event to broadcast.
        data: Optional data payload to send with the event.
    """
    logging.debug("Broadcasting event: " + event)
    emit(event, data, namespace="/", broadcast=True)
