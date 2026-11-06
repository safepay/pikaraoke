"""Singer-facing API. Favourites and self-service rename; preferences join later."""

import math

import flask_babel
from flask import jsonify, request
from flask_smorest import Blueprint
from marshmallow import Schema, ValidationError, fields, post_load, validate

from pikaraoke.lib.auth import log_in_singer, public
from pikaraoke.lib.current_app import (
    clear_singer_session,
    current_singer_id,
    current_singer_name,
    get_karaoke_instance,
    grant_singer_session,
    singer_lock_barrier,
)
from pikaraoke.lib.singer_manager import SINGER_NAME_MAX_LENGTH, normalize_name

_ = flask_babel.gettext

singers_api_bp = Blueprint("singers_api", __name__)


def _lock_refusal(barrier: str):
    """A refusal the client turns into the password dialog, by lock-barrier reason."""
    if barrier == "locked":
        # MSG: Error when acting under a password-protected name without being logged in to it.
        msg = _("This name is protected. Enter its password to continue.")
    else:
        # MSG: Error when a name needs a password set before it can be used (enforcement on).
        msg = _("This name needs a password. Set one to continue.")
    return jsonify({"success": False, "auth_required": True, "error": msg})


class FavouriteForm(Schema):
    song = fields.String(required=True, metadata={"description": "Path to the song file"})
    starred = fields.Boolean(required=True, metadata={"description": "Desired favourite state"})
    # The singer the star belongs to, resolved client-side exactly as a queue add
    # resolves it (the cookie, else the Join in dialog), so the two agree on a name.
    song_added_by = fields.String(required=True, metadata={"description": "The singer's name"})

    @post_load
    def clean_name(self, data, **kwargs):
        # Same normalisation as a queue add, so a star and a play agree on a name.
        name = normalize_name(data["song_added_by"])
        if not name:
            # MSG: Error when a song is favourited without a name.
            raise ValidationError(_("A name is required"), "song_added_by")
        if len(name) > SINGER_NAME_MAX_LENGTH:
            # MSG: Error when a favouriting name is longer than the limit.
            raise ValidationError(
                _("Name must be %(max)d characters or fewer", max=SINGER_NAME_MAX_LENGTH),
                "song_added_by",
            )
        if "<" in name or ">" in name:
            # MSG: Error when a singer name contains disallowed HTML angle brackets
            raise ValidationError(_("Invalid singer name"), "song_added_by")
        data["song_added_by"] = name
        return data


@singers_api_bp.route("/api/singer/favourite", methods=["POST"])
@public
@singers_api_bp.arguments(FavouriteForm, location="form")
def set_favourite(form):
    """Star or unstar a song for the named singer.

    Open to the room: a favourite borrows no privilege, and the name is the
    singer's own, exactly as a queue add is.
    """
    k = get_karaoke_instance()
    name = form["song_added_by"]
    # A merged name is retired, as at the queue add.
    survivor = k.singer_manager.merged_into_name(name)
    if survivor:
        # MSG: Error when starring under a name the host merged into another. %(name)s is the surviving name.
        error = _("This name was merged into %(name)s. Set your name to continue.", name=survivor)
        return jsonify({"success": False, "error": error})
    barrier = singer_lock_barrier(k, name)
    if barrier:
        return _lock_refusal(barrier)
    if form["starred"]:
        k.singer_manager.add_favourite(name, form["song"])
    else:
        k.singer_manager.remove_favourite(name, form["song"])
    return jsonify({"success": True, "starred": form["starred"]})


def _clean_singer_name(raw: str, field: str) -> str:
    """Normalise and bound a singer name, the same rule the queue add applies."""
    name = normalize_name(raw)
    if not name:
        # MSG: Error when a rename is submitted without a new name.
        raise ValidationError(_("A name is required"), field)
    if len(name) > SINGER_NAME_MAX_LENGTH:
        # MSG: Error when a renaming name is longer than the limit.
        raise ValidationError(
            _("Name must be %(max)d characters or fewer", max=SINGER_NAME_MAX_LENGTH), field
        )
    if "<" in name or ">" in name:
        # MSG: Error when a singer name contains disallowed HTML angle brackets
        raise ValidationError(_("Invalid singer name"), field)
    return name


class RenameForm(Schema):
    old_name = fields.String(required=True, metadata={"description": "The singer's current name"})
    new_name = fields.String(required=True, metadata={"description": "The name to move to"})

    @post_load
    def clean(self, data, **kwargs):
        # old_name is only ever matched against the caller's cookie, so it needs
        # the same canonical form but not the blank/length refusal -- a bad old
        # name simply fails that match.
        data["old_name"] = normalize_name(data["old_name"])
        data["new_name"] = _clean_singer_name(data["new_name"], "new_name")
        return data


@singers_api_bp.route("/api/singer/rename", methods=["POST"])
@public
@singers_api_bp.arguments(RenameForm, location="form")
def rename_singer(form):
    """Rename the singer this device is holding, carrying everything they own.

    Open to the room, but you can only rename the name in your own cookie: the
    rename rewrites this device's name on success, so a request for any other
    name has no device to re-home and is refused. Renaming onto a free name
    moves the queue, the song on screen, history and favourites together;
    renaming onto a name that already owns data is a merge, which is the admin's.
    """
    cookie = current_singer_name()
    if cookie is None or normalize_name(cookie).lower() != form["old_name"].lower():
        # MSG: Error when a device tries to rename a name it is not holding.
        return jsonify({"success": False, "error": _("You can only change your own name")}), 403

    k = get_karaoke_instance()
    # A protected name only moves from a device logged in as it.
    if k.singer_manager.is_protected(form["old_name"]) and singer_lock_barrier(k, form["old_name"]):
        return _lock_refusal("locked"), 403
    outcome = k.rename_singer(form["old_name"], form["new_name"])
    if outcome == "taken":
        # MSG: Error when renaming onto a name that already belongs to someone else.
        return jsonify({"success": False, "error": _("That name is already taken")}), 409
    if outcome == "reserved":
        # MSG: Error when renaming to or from a reserved system name.
        return jsonify({"success": False, "error": _("That name is reserved")}), 409
    return jsonify({"success": True, "name": form["new_name"], "action": outcome})


# ----------------------------------------------------------------------
# The name lock: a singer claims, proves and manages their own password
# ----------------------------------------------------------------------


def _authed_as(name: str) -> bool:
    """Whether this device is logged in as the singer holding `name`."""
    singer = get_karaoke_instance().singer_manager.find(name)
    return bool(singer and current_singer_id() == singer["id"])


class PasswordForm(Schema):
    name = fields.String(required=True, metadata={"description": "The name to protect"})
    # Empty clears the lock, which only the logged-in singer may do.
    password = fields.String(
        load_default="", metadata={"description": "New password; empty clears"}
    )

    @post_load
    def clean(self, data, **kwargs):
        data["name"] = _clean_singer_name(data["name"], "name")
        return data


@singers_api_bp.route("/api/singer/password", methods=["POST"])
@public
@singers_api_bp.arguments(PasswordForm, location="form")
def set_password(form):
    """Claim a name with a password, or change or clear an existing lock.

    An unprotected name is open to claim -- setting the password is the claim.
    Changing or clearing an existing lock needs this device logged in as it. On
    success this device is granted (or kept in) the singer session; the client
    writes the name cookie.
    """
    k = get_karaoke_instance()
    name, password = form["name"], form["password"]
    singers = k.singer_manager
    if singers.is_protected(name) and not _authed_as(name):
        # MSG: Error when changing a protected name's password without being logged in to it.
        return jsonify({"success": False, "error": _("Log in to change this password")}), 403
    if not password:
        singers.clear_password(name)
        return jsonify({"success": True, "name": name, "protected": False})
    singer_id = singers.set_password(name, password)
    grant_singer_session(singer_id, singers.session_token(singer_id))
    return jsonify({"success": True, "name": name, "protected": True})


class LoginForm(Schema):
    name = fields.String(required=True, metadata={"description": "The protected name"})
    password = fields.String(required=True, metadata={"description": "The name's password"})

    @post_load
    def clean(self, data, **kwargs):
        data["name"] = normalize_name(data["name"])
        return data


@singers_api_bp.route("/api/singer/login", methods=["POST"])
@public
@singers_api_bp.arguments(LoginForm, location="form")
def login_singer(form):
    """Log this device in to a protected name; the client writes the name cookie."""
    outcome = log_in_singer(form["name"], form["password"])
    if outcome.granted:
        # The canonical stored name, so a login under a different casing adopts the
        # owner's chosen one rather than overwriting it on the next play.
        return jsonify({"success": True, "name": outcome.name})
    if outcome.throttled:
        response = jsonify({"success": False, "error": _("Too many attempts")})
        response.status_code = 429
        response.headers["Retry-After"] = str(math.ceil(outcome.retry_after))
        return response
    # MSG: Error shown when a singer's password is wrong.
    return jsonify({"success": False, "error": _("Incorrect password")}), 401


@singers_api_bp.route("/api/singer/logout", methods=["POST"])
@public
def logout_singer():
    """Drop this device's singer login; the name cookie is the client's to clear."""
    clear_singer_session()
    return jsonify({"success": True})


@singers_api_bp.route("/api/singer/status")
@public
def singer_status():
    """Report a name's lock state for the identity dialog: is it protected, is this
    device logged in to it, and is a password required to use any name."""
    k = get_karaoke_instance()
    name = normalize_name(request.args.get("name") or current_singer_name() or "")
    return jsonify(
        {
            "name": name,
            "protected": bool(name) and k.singer_manager.is_protected(name),
            "authenticated": bool(name) and _authed_as(name),
            "required": bool(getattr(k, "require_singer_password", False)),
        }
    )


# ----------------------------------------------------------------------
# The admin Singers page: the roster, and the two acts only an operator performs
# ----------------------------------------------------------------------


class MergeForm(Schema):
    loser = fields.String(required=True, metadata={"description": "The name being folded away"})
    survivor = fields.String(required=True, metadata={"description": "The name that is kept"})


class DeleteForm(Schema):
    names = fields.List(
        fields.String(),
        required=True,
        validate=validate.Length(min=1),
        metadata={"description": "The singers to delete, each with no plays"},
    )


@singers_api_bp.route("/api/singers")
def get_roster():
    """The singer roster for the admin page (admin only)."""
    k = get_karaoke_instance()
    return jsonify({"singers": k.singer_manager.get_roster()})


@singers_api_bp.route("/api/singer/merge", methods=["POST"])
@singers_api_bp.arguments(MergeForm, location="json")
def merge_singers(form):
    """Fold one singer into another, tombstoning the loser (admin only)."""
    k = get_karaoke_instance()
    outcome = k.merge_singers(form["loser"], form["survivor"])
    if outcome == "reserved":
        # MSG: Error when merging a reserved system name.
        return jsonify({"success": False, "error": _("That name is reserved")}), 409
    if outcome != "merged":
        # MSG: Error when a singer named for a merge or delete no longer exists.
        return jsonify({"success": False, "error": _("Singer not found")}), 404
    return jsonify({"success": True})


@singers_api_bp.route("/api/singer/delete", methods=["POST"])
@singers_api_bp.arguments(DeleteForm, location="json")
def delete_singers(form):
    """Delete singers that own no plays (admin only); reports how many were removed."""
    k = get_karaoke_instance()
    deleted = sum(1 for name in form["names"] if k.singer_manager.delete_singer(name))
    return jsonify({"success": True, "deleted": deleted, "requested": len(form["names"])})


@singers_api_bp.route("/api/singer/clear-lock", methods=["POST"])
@singers_api_bp.arguments(DeleteForm, location="json")
def clear_locks(form):
    """Clear the password lock on the named singers (admin only), keeping their data.

    Nulling the lock rotates session_token(), so each singer's other devices are
    logged out; they re-protect the name with one of their own choosing.
    """
    k = get_karaoke_instance()
    cleared = sum(1 for name in form["names"] if k.singer_manager.clear_password(name))
    return jsonify({"success": True, "cleared": cleared, "requested": len(form["names"])})
