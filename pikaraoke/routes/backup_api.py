"""API for database backup, restore and the whole-database reset.

Admin-only by default (the host gate covers every unmarked route). Every route is
POST, including the reads and the downloads: a cookie-authenticated GET can be
fired cross-site by a link, image or prefetch, and a backup is the whole library.
Downloads return the dump bytes for the browser to save, so no route serves a
file by a navigable URL. Restore and reset overwrite the database, so each takes
the current state down first unless the caller opts out.
"""

import json
import logging
import os

import flask_babel
from flask import Response, jsonify, request
from flask_smorest import Blueprint

from pikaraoke.lib.current_app import get_karaoke_instance
from pikaraoke.lib.db_backup import BackupVersionError

_ = flask_babel.gettext

backup_api_bp = Blueprint("backup_api", __name__)


def _wants_backup_first() -> bool:
    """Whether to snapshot the current database before overwriting it (default yes)."""
    raw = (request.form.get("backup_first") or "true").lower()
    return raw not in ("false", "0", "no", "off")


def _backup_first_or_abort(k):
    """Snapshot the current database; return an error Response if that fails."""
    if not _wants_backup_first():
        return None
    try:
        k.backup_manager.create_backup()
        return None
    except (OSError, ValueError) as e:
        logging.error(f"Pre-restore backup failed, aborting: {e}")
        return jsonify(
            {
                "success": False,
                "error": _("Could not back up the current database. Nothing changed."),
            }
        )


def _attachment(data: str, name: str) -> Response:
    return Response(
        data,
        mimetype="application/json",
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )


@backup_api_bp.route("/api/backups/list", methods=["POST"])
def list_backups():
    """The backups on the server, newest first, for the settings list."""
    k = get_karaoke_instance()
    return jsonify(
        {"backups": k.backup_manager.list_backups(), "path": k.backup_manager.backup_dir}
    )


@backup_api_bp.route("/api/backups", methods=["POST"])
def backup_now():
    """Write a server-side backup unless the database is unchanged since the last.

    Skipping the write keeps the retention pool from filling with identical
    files, the same way the startup backup does. Download is the separate action.
    """
    k = get_karaoke_instance()
    try:
        path = k.backup_manager.backup_if_changed()
    except (OSError, ValueError) as e:
        logging.error(f"Backup failed: {e}")
        return jsonify({"success": False, "error": _("Backup failed")}), 500
    if path is None:
        return jsonify({"success": True, "unchanged": True})
    return jsonify({"success": True, "name": os.path.basename(path)})


@backup_api_bp.route("/api/backups/<name>/download", methods=["POST"])
def download_backup(name):
    """Hand an earlier server backup back as a file for off-machine safekeeping."""
    k = get_karaoke_instance()
    try:
        path = k.backup_manager.path_for(name)
    except ValueError:
        return jsonify({"success": False, "error": _("Invalid backup name")}), 400
    if not os.path.isfile(path):
        return jsonify({"success": False, "error": _("Backup not found")}), 404
    with open(path, encoding="utf-8") as f:
        return _attachment(f.read(), name)


@backup_api_bp.route("/api/backups/<name>/delete", methods=["POST"])
def delete_backup(name):
    """Delete one server-side backup, leaving the database and the rest untouched."""
    k = get_karaoke_instance()
    try:
        path = k.backup_manager.path_for(name)
    except ValueError:
        return jsonify({"success": False, "error": _("Invalid backup name")}), 400
    if not os.path.isfile(path):
        return jsonify({"success": False, "error": _("Backup not found")}), 404
    try:
        k.backup_manager.delete_backup(name)
    except OSError as e:
        logging.error(f"Could not delete backup {name}: {e}")
        return jsonify({"success": False, "error": _("Could not delete the backup")}), 500
    return jsonify({"success": True})


@backup_api_bp.route("/api/backups/<name>/restore", methods=["POST"])
def restore_backup(name):
    """Restore the database from a server-side backup, then resync."""
    k = get_karaoke_instance()
    try:
        k.backup_manager.path_for(name)  # validate the name before reading
    except ValueError:
        return jsonify({"success": False, "error": _("Invalid backup name")}), 400
    try:
        dump = k.backup_manager.read_backup(name)
    except (OSError, json.JSONDecodeError):
        return jsonify({"success": False, "error": _("Backup not found or unreadable")}), 404
    return _restore(k, dump)


@backup_api_bp.route("/api/backups/restore-upload", methods=["POST"])
def restore_upload():
    """Restore from a dump uploaded from off the machine."""
    k = get_karaoke_instance()
    uploaded = request.files.get("file")
    if uploaded is None:
        return jsonify({"success": False, "error": _("No backup file was uploaded")}), 400
    try:
        dump = json.loads(uploaded.read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return jsonify({"success": False, "error": _("That file is not a PiKaraoke backup")}), 400
    return _restore(k, dump)


@backup_api_bp.route("/api/database/reset", methods=["POST"])
def reset_database():
    """Erase the whole database, rebuilding the song index from the files."""
    k = get_karaoke_instance()
    aborted = _backup_first_or_abort(k)
    if aborted is not None:
        return aborted, 500
    k.reset_database()
    return jsonify({"success": True})


def _restore(k, dump):
    """Shared restore path: back up first, replace, resync -- or report why not."""
    aborted = _backup_first_or_abort(k)
    if aborted is not None:
        return aborted, 500
    try:
        k.restore_database(dump)
    except BackupVersionError as e:
        return jsonify({"success": False, "error": str(e)}), 409
    return jsonify({"success": True})
