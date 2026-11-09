"""Server-side database backups: write, list, prune and locate dump files.

Dumps are JSON files named ``pikaraoke-backup-YYYYMMDD-HHMMSS.json`` so they sort
by time. Restore itself lives in db_backup; this owns the directory.
"""

import logging
import os
from datetime import datetime
from typing import Any, Callable

from pikaraoke.lib import db_backup
from pikaraoke.lib.karaoke_database import KaraokeDatabase

_PREFIX = "pikaraoke-backup-"
_SUFFIX = ".json"


def is_backup_filename(name: str) -> bool:
    return name.startswith(_PREFIX) and name.endswith(_SUFFIX)


class BackupManager:
    """Owns the backups directory: writing dumps, retention and safe lookup."""

    def __init__(
        self,
        db: KaraokeDatabase,
        backup_dir: str,
        get_keep_count: Callable[[], int],
    ) -> None:
        self._db = db
        self._backup_dir = backup_dir
        self._get_keep_count = get_keep_count

    @property
    def backup_dir(self) -> str:
        return self._backup_dir

    def create_backup(self) -> str:
        """Write a dump of the durable tables now; return its path."""
        return self._write(db_backup.build_dump(self._db))

    def startup_backup(self) -> str | None:
        """Back up at startup, skipping when the database is unchanged.

        A run of restarts with nothing played must not fill the retention pool
        with identical files and evict the older, more varied states.
        """
        dump = db_backup.build_dump(self._db)
        existing = self._backup_paths()
        if existing:
            try:
                newest = db_backup.load_dump(_read(existing[0]))
                if db_backup.dump_fingerprint(newest) == db_backup.dump_fingerprint(dump):
                    logging.info("Startup backup skipped: database unchanged since last backup")
                    return None
            except (OSError, ValueError) as e:
                logging.warning(f"Could not read newest backup to compare: {e}")
        return self._write(dump)

    def list_backups(self) -> list[dict[str, Any]]:
        """Describe the backups newest first: name, time, counts and size."""
        items: list[dict[str, Any]] = []
        for path in self._backup_paths():
            info: dict[str, Any] = {
                "name": os.path.basename(path),
                "size": os.path.getsize(path),
                "created_at": None,
                "app_version": None,
                "schema_version": None,
                "song_count": None,
            }
            try:
                dump = db_backup.load_dump(_read(path))
                info["created_at"] = dump.get("created_at")
                info["app_version"] = dump.get("app_version")
                info["schema_version"] = dump.get("schema_version")
                info["song_count"] = len(dump.get("tables", {}).get("songs", []))
            except (OSError, ValueError) as e:
                logging.warning(f"Unreadable backup {info['name']}: {e}")
            items.append(info)
        return items

    def read_backup(self, name: str) -> dict[str, Any]:
        """Load a named backup for restore, rejecting any path outside the dir."""
        return db_backup.load_dump(_read(self.path_for(name)))

    def path_for(self, name: str) -> str:
        """Resolve a client-supplied filename to a safe path in the backup dir."""
        if os.path.basename(name) != name or not is_backup_filename(name):
            raise ValueError(f"Not a backup filename: {name!r}")
        return os.path.join(self._backup_dir, name)

    def prune(self) -> None:
        """Keep the newest N backups, delete the rest."""
        keep = max(1, int(self._get_keep_count()))
        for path in self._backup_paths()[keep:]:
            try:
                os.remove(path)
            except OSError as e:
                logging.warning(f"Could not prune backup {path}: {e}")

    def _write(self, dump: dict[str, Any]) -> str:
        os.makedirs(self._backup_dir, exist_ok=True)
        path = self._unique_path(datetime.now())
        with open(path, "w", encoding="utf-8") as f:
            f.write(db_backup.dump_to_json(dump))
        logging.info(f"Wrote database backup: {path}")
        self.prune()
        return path

    def _unique_path(self, when: datetime) -> str:
        stem = _PREFIX + when.strftime("%Y%m%d-%H%M%S")
        path = os.path.join(self._backup_dir, stem + _SUFFIX)
        counter = 1
        while os.path.exists(path):
            path = os.path.join(self._backup_dir, f"{stem}-{counter}{_SUFFIX}")
            counter += 1
        return path

    def _backup_paths(self) -> list[str]:
        try:
            names = [n for n in os.listdir(self._backup_dir) if is_backup_filename(n)]
        except OSError:
            return []
        return [os.path.join(self._backup_dir, n) for n in sorted(names, reverse=True)]


def _read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()
