# Stage 1: Core Database Layer - Implementation Plan

**Stage:** 1 of 4
**Status:** Ready for Implementation
**Prerequisites:** Stage 0 (Complete)
**Estimated Effort:** 1-2 days
**Risk Level:** Low

## Objective

Create a standalone, fully-tested database layer (`KaraokeDatabase` class) that:

1. Initializes SQLite database with proper schema and WAL mode
2. Synchronizes library with disk (detect adds/moves/deletes)
3. Creates and restores database backups
4. Validates database integrity

**Critical Requirement:** Works in isolation without app integration (integrated in Stage 2).

## Deliverables

### Core Module

**File:** `pikaraoke/lib/karaoke_database.py`

**Public Methods:**

```python
from __future__ import annotations


class KaraokeDatabase:
    def __init__(
        self, db_path: str | None = None, backup_dir: str | None = None
    ) -> None:
        """Initialize database connection."""

    def scan_library(self, songs_dir: str) -> dict[str, int]:
        """Scan library and return stats dict."""

    def create_backup_file(self) -> str | None:
        """Create backup and return path or None on error."""

    def restore_from_file(self, uploaded_file_path: str) -> tuple[bool, str]:
        """Restore database from backup file."""

    def check_integrity(self) -> tuple[bool, str]:
        """Validate database integrity."""

    def get_all_song_paths(self) -> list[str]:
        """Get list of all song file paths."""

    def get_song_count(self) -> int:
        """Get total number of visible songs."""

    def close(self) -> None:
        """Close database connection gracefully."""
```

### Unit Tests

**File:** `tests/test_karaoke_database.py`

Test coverage: initialization, schema, scanning (adds/moves/deletes), CDG/ASS pairing, hash
generation, backup/restore, integrity checking, Unicode filenames.

## Schema Design

```sql
-- Schema Version: 1
PRAGMA user_version = 1;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS songs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE NOT NULL,
    file_hash TEXT,
    filename TEXT NOT NULL,
    artist TEXT,
    title TEXT,
    variant TEXT,
    year INTEGER,
    genre TEXT,
    youtube_id TEXT,
    format TEXT NOT NULL,
    search_blob TEXT,
    is_visible INTEGER DEFAULT 1,
    metadata_status TEXT DEFAULT 'pending',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_file_hash ON songs(file_hash);
CREATE INDEX IF NOT EXISTS idx_metadata_status ON songs(metadata_status);
CREATE INDEX IF NOT EXISTS idx_artist ON songs(artist);
CREATE INDEX IF NOT EXISTS idx_title ON songs(title);
CREATE INDEX IF NOT EXISTS idx_search_blob ON songs(search_blob);
CREATE INDEX IF NOT EXISTS idx_is_visible ON songs(is_visible);

CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

## File Format Detection

```python
from __future__ import annotations

import os

VALID_EXTENSIONS = {".mp4", ".mp3", ".zip", ".mkv", ".avi", ".webm", ".mov"}


def detect_format(file_path: str, files_in_dir: set[str]) -> str | None:
    """Detect song format with pairing logic.

    Args:
        file_path: Full path to the file
        files_in_dir: Set of lowercase filenames in same directory

    Returns:
        Format string or None if not valid
    """
    base, ext = os.path.splitext(file_path)
    basename = os.path.basename(base)
    ext = ext.lower()

    if ext not in VALID_EXTENSIONS:
        return None

    # CDG pairing: MP3 + CDG
    if ext == ".mp3" and (basename.lower() + ".cdg") in files_in_dir:
        return "CDG"

    # ZIP archives
    if ext == ".zip":
        return "ZIP"

    # Video with subtitle pairing
    if ext in {".mp4", ".mkv", ".avi", ".webm", ".mov"}:
        if (basename.lower() + ".ass") in files_in_dir:
            return ext[1:].upper() + "+ASS"
        return ext[1:].upper()

    # Standalone MP3
    if ext == ".mp3":
        return "MP3"

    return None
```

**Important:** Only the primary file (e.g., `.mp3` from CDG pair) is added to the database.

## Hash Generation

**Algorithm:** SHA256 of (file_size + first 16KB)

```python
from __future__ import annotations

import hashlib
import logging
import os


def get_fingerprint(file_path: str) -> str | None:
    """Generate content fingerprint for move detection.

    Args:
        file_path: Full path to the file

    Returns:
        SHA256 hash string or None on error
    """
    try:
        stats = os.stat(file_path)
        with open(file_path, "rb") as f:
            header = f.read(16384)

        hasher = hashlib.sha256()
        hasher.update(str(stats.st_size).encode("utf-8"))
        hasher.update(header)
        return hasher.hexdigest()
    except Exception as e:
        logging.warning(f"Failed to generate hash for {file_path}: {e}")
        return None
```

## Scan Library Algorithm

**Goal:** Synchronize database with disk, detecting adds/moves/deletes/updates.

```python
from __future__ import annotations


def scan_library(self, songs_dir: str) -> dict[str, int]:
    """Scan library and sync database.

    Args:
        songs_dir: Directory containing song files

    Returns:
        Stats dict: added, moved, deleted, updated
    """
    # 1. Discover files on disk
    disk_files = {}  # {rel_path: (filename, format, hash)}
    for file in walk(songs_dir):
        if is_valid_song(file):
            format = detect_format(file, files_in_same_dir)
            if format:
                rel_path = relative_path(file, songs_dir)
                hash = get_fingerprint(file)
                disk_files[rel_path] = (filename, format, hash)

    # 2. Fetch database state
    db_rows = fetch_all_from_db()  # {file_path: row}

    # 3. Compare sets
    disk_paths = set(disk_files.keys())
    db_paths = set(db_rows.keys())

    common_paths = disk_paths & db_paths
    new_paths = disk_paths - db_paths
    missing_paths = db_paths - disk_paths

    # 4. Update existing files
    for path in common_paths:
        disk_filename, disk_format, disk_hash = disk_files[path]
        db_row = db_rows[path]

        if disk_hash != db_row["file_hash"] or disk_format != db_row["format"]:
            update_song(db_row["id"], hash=disk_hash, format=disk_format)
            stats["updated"] += 1

    # 5. Detect moves vs deletes
    missing_by_hash = {
        db_rows[p]["file_hash"]: db_rows[p]
        for p in missing_paths
        if db_rows[p]["file_hash"]
    }

    moved_paths = set()

    for new_path in new_paths:
        new_filename, new_format, new_hash = disk_files[new_path]

        if new_hash and new_hash in missing_by_hash:
            old_row = missing_by_hash[new_hash]
            update_song(old_row["id"], file_path=new_path, filename=new_filename)
            moved_paths.add(new_path)
            del missing_by_hash[new_hash]
            stats["moved"] += 1
        else:
            insert_song(new_path, new_filename, new_format, new_hash)
            stats["added"] += 1

    # 6. Delete truly missing files
    for hash, row in missing_by_hash.items():
        delete_song(row["id"])
        stats["deleted"] += 1

    for path in missing_paths:
        if db_rows[path]["file_hash"] is None:
            delete_song(db_rows[path]["id"])
            stats["deleted"] += 1

    # 7. Update timestamp
    update_metadata("last_scan", datetime.now().isoformat())
    commit()

    return stats
```

## Search Blob

```python
from __future__ import annotations

import os


def build_search_blob(
    filename: str,
    title: str | None = None,
    artist: str | None = None,
    youtube_id: str | None = None,
) -> str:
    """Build searchable text blob.

    Args:
        filename: Song filename
        title: Song title
        artist: Artist name
        youtube_id: YouTube video ID

    Returns:
        Lowercase searchable string
    """
    parts = []

    clean_name = os.path.splitext(filename)[0].replace("_", " ")
    parts.append(clean_name)

    if title and title != clean_name:
        parts.append(title)

    if artist:
        parts.append(artist)

    if youtube_id:
        parts.append(youtube_id)

    return " ".join(parts).lower()
```

## Backup and Restore

### Create Backup

```python
from __future__ import annotations

import logging
import os
import sqlite3
from datetime import datetime


def create_backup_file(self) -> str | None:
    """Create database snapshot.

    Returns:
        Path to backup file or None on error
    """
    try:
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)

        timestamp = datetime.now().strftime("pikaraoke_backup_%Y%m%d_%H%M%S.db")
        backup_path = os.path.join(self.backup_dir, timestamp)

        backup_conn = sqlite3.connect(backup_path)
        self.conn.backup(backup_conn)
        backup_conn.close()

        logging.info(f"Backup created: {backup_path}")
        return backup_path
    except Exception as e:
        logging.error(f"Backup creation failed: {e}")
        return None
```

### Restore from Backup

```python
from __future__ import annotations

import logging
import os
import shutil
import sqlite3


def restore_from_file(self, uploaded_file_path: str) -> tuple[bool, str]:
    """Restore database from backup.

    Args:
        uploaded_file_path: Path to uploaded .db file

    Returns:
        (success: bool, message: str)
    """
    # Validate file
    if not os.path.exists(uploaded_file_path):
        return False, "Upload file not found"

    try:
        with open(uploaded_file_path, "rb") as f:
            header = f.read(16)
        if b"SQLite format 3" not in header:
            return False, "Invalid file format"
    except Exception as e:
        return False, f"File validation error: {e}"

    # Validate schema
    try:
        test_conn = sqlite3.connect(uploaded_file_path)
        version = test_conn.execute("PRAGMA user_version").fetchone()[0]
        test_conn.close()

        if version != DB_VERSION:
            return False, f"Incompatible version: {version}"
    except Exception as e:
        return False, f"Schema validation error: {e}"

    try:
        if self.conn:
            self.conn.close()

        # Clean up old DB files
        for ext in ["", "-wal", "-shm"]:
            target = self.db_path + ext
            if os.path.exists(target):
                try:
                    os.remove(target)
                except OSError as e:
                    logging.warning(f"Failed to remove {target}: {e}")

        shutil.copy2(uploaded_file_path, self.db_path)
        self._connect()

        logging.info("Database restored successfully")
        return True, "Restore successful"

    except Exception as e:
        try:
            self._connect()
        except Exception:
            pass

        logging.error(f"Restore failed: {e}")
        return False, f"Restore failed: {e}"
```

## Integrity Check

```python
from __future__ import annotations


def check_integrity(self) -> tuple[bool, str]:
    """Validate database integrity.

    Returns:
        (is_valid: bool, message: str)
    """
    try:
        result = self.conn.execute("PRAGMA integrity_check").fetchone()[0]

        if result == "ok":
            return True, "Database integrity: OK"
        return False, f"Database integrity issues: {result}"

    except Exception as e:
        return False, f"Integrity check failed: {e}"
```

## Helper Methods

```python
from __future__ import annotations


def get_all_song_paths(self) -> list[str]:
    """Get list of all song file paths.

    Returns:
        List of file paths sorted by filename
    """
    cursor = self.conn.execute(
        "SELECT file_path FROM songs WHERE is_visible = 1 ORDER BY filename"
    )
    return [row[0] for row in cursor.fetchall()]


def get_song_count(self) -> int:
    """Get total number of songs.

    Returns:
        Count of visible songs
    """
    cursor = self.conn.execute("SELECT COUNT(*) FROM songs WHERE is_visible = 1")
    return cursor.fetchone()[0]


def close(self) -> None:
    """Close database connection gracefully."""
    if self.conn:
        self.conn.close()
        self.conn = None
```

## Testing Plan

### Unit Test Cases

```python
from __future__ import annotations

import os
import tempfile

import pytest

from pikaraoke.lib.karaoke_database import KaraokeDatabase


class TestKaraokeDatabase:
    def test_initialization(self):
        """Test database initialization."""

    def test_schema_creation(self):
        """Verify tables and indices exist."""

    def test_scan_empty_directory(self):
        """Test scanning empty directory."""

    def test_scan_adds_files(self):
        """Test detecting new files."""

    def test_scan_detects_moves(self):
        """Test move detection via hash."""

    def test_scan_detects_deletes(self):
        """Test detecting deleted files."""

    def test_scan_detects_updates(self):
        """Test detecting content changes."""

    def test_cdg_pairing(self):
        """Test CDG format detection."""

    def test_ass_subtitle_pairing(self):
        """Test subtitle pairing."""

    def test_unicode_filenames(self):
        """Test Unicode filename handling."""

    def test_backup_creation(self):
        """Test backup file creation."""

    def test_restore_from_backup(self):
        """Test restore functionality."""

    def test_restore_invalid_file(self):
        """Test rejecting invalid files."""

    def test_integrity_check_valid(self):
        """Test integrity check on valid DB."""

    def test_get_all_song_paths(self):
        """Test retrieving song paths."""

    def test_get_song_count(self):
        """Test song counting."""
```

### Edge Cases

01. Empty directory
02. Permission errors
03. Symlinks
04. Hidden files
05. Large files
06. Hash collisions
07. Concurrent access
08. Database deletion
09. Partial scan interruption
10. Unicode edge cases

## Success Criteria

- Database initializes with correct schema
- WAL mode enabled
- `scan_library()` returns accurate stats
- New files added correctly
- Moved files detected (not deleted+added)
- Deleted files removed
- CDG/ASS pairs detected correctly
- Hash generation fast (\< 50ms per file)
- Backup files valid
- Restore operation safe
- Integrity check validates health
- All unit tests pass
- No memory leaks
- Handles Unicode correctly
- Graceful permission error handling

## Error Handling

All methods must:

1. Never crash the app
2. Log errors using Python logging
3. Return meaningful error messages
4. Fail safely

Example:

```python
from __future__ import annotations

import logging


def scan_library(self, songs_dir: str) -> dict[str, int]:
    """Scan library and sync database.

    Args:
        songs_dir: Directory to scan

    Returns:
        Stats dict or all zeros on error
    """
    try:
        # Implementation
        pass
    except Exception as e:
        logging.error(f"Scan failed: {e}")
        return {"added": 0, "moved": 0, "deleted": 0, "updated": 0}
```

## Performance Targets

| Library Size  | Initial Scan | Subsequent Scan | Memory Usage |
| ------------- | ------------ | --------------- | ------------ |
| 100 songs     | \< 2s         | \< 0.5s          | ~5 MB        |
| 1,000 songs   | \< 10s        | \< 2s            | ~10 MB       |
| 10,000 songs  | \< 60s        | \< 10s           | ~50 MB       |

Optimizations: batch commits, prepared statements, index usage, lazy loading, hash caching.

## Integration Preview (Stage 2)

```python
from __future__ import annotations

import logging

from pikaraoke.lib.karaoke_database import KaraokeDatabase


class Karaoke:
    def __init__(self, ...):
        """Initialize Karaoke application."""
        # Existing init code

        # Initialize database (Stage 2)
        self.db = KaraokeDatabase()

        # Scan library on startup
        stats = self.db.scan_library(self.download_path)
        logging.info(f"Library scan: {stats}")

        # Populate legacy SongList
        self.available_songs = SongList()
        self.available_songs.update(self.db.get_all_song_paths())
```

## Next Steps

After Stage 1 completion:

1. All unit tests pass
2. Code review completed
3. Performance benchmarks met
4. Documentation complete
5. Proceed to Stage 2 (App Integration)

**Document Status:** Ready for Implementation
**Last Updated:** 2026-01-11
