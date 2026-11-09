"""Logical backup and restore of the durable database tables.

The song index is regenerable from the media files by a sync; the durable
stratum -- tuned metadata, enrichment state, suggestion staging, play history,
singers and their choices -- lives only here. This serialises that stratum to a
versioned JSON dump and restores it as one whole-graph replacement, ids and all,
so foreign keys come back pointing where they did. A sync afterwards trues the
restored file paths up against what is on disk.
"""

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from pikaraoke.lib.karaoke_database import KaraokeDatabase
from pikaraoke.version import __version__ as VERSION

# Parents before children for readable dumps. `metadata` is excluded: its one
# entry, the last scan directory, is reset by the sync after a restore. Which
# tables are durable is the judgement a schema change revisits here; the columns
# within each are read from the rows.
DURABLE_TABLES: tuple[str, ...] = (
    "songs",
    "sessions",
    "singers",
    "plays",
    "singer_songs",
    "singer_preferences",
)


class BackupVersionError(Exception):
    """A dump taken on a newer schema than this build can load."""


def build_dump(db: KaraokeDatabase) -> dict[str, Any]:
    """Serialise the durable tables to a dump dict, header and all."""
    return {
        "schema_version": db.schema_version,
        "app_version": VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "tables": db.snapshot_tables(list(DURABLE_TABLES)),
    }


def dump_to_json(dump: dict[str, Any]) -> str:
    """Render a dump as indented JSON, kept readable for inspection."""
    return json.dumps(dump, ensure_ascii=False, indent=2)


def load_dump(text: str) -> dict[str, Any]:
    """Parse a dump from its JSON text."""
    return json.loads(text)


def restore_dump(db: KaraokeDatabase, dump: dict[str, Any]) -> None:
    """Replace the durable tables from a dump, refusing a newer schema.

    A newer dump may carry columns this build has no home for, so it is refused
    rather than silently dropping them. An older dump loads fine: its missing
    columns take their schema defaults.
    """
    version = dump.get("schema_version")
    if version is None or version > db.schema_version:
        raise BackupVersionError(
            f"This backup was taken on schema version {version}, newer than this "
            f"version of PiKaraoke supports (version {db.schema_version}). "
            "Upgrade PiKaraoke, then restore."
        )
    db.replace_tables(dump.get("tables", {}))


def dump_fingerprint(dump: dict[str, Any]) -> str:
    """A content hash of the rows alone, so two dumps of an unchanged database
    match despite their fresh header timestamps."""
    payload = json.dumps(dump.get("tables", {}), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
