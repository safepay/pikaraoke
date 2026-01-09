# Stage 1: Core Database Layer - Detailed Implementation Plan

**Stage:** 1 of 4
**Status:**  Ready for Implementation
**Prerequisites:** Stage 0 (Complete)
**Estimated Effort:** 1-2 days
**Risk Level:** Low

______________________________________________________________________

## Objective

Create a standalone, fully-tested database layer (`KaraokeDatabase` class) that can:

1. Initialize SQLite database with proper schema and WAL mode
2. Synchronize library with disk (detect adds/moves/deletes)
3. Create and restore database backups safely
4. Validate database integrity

**Critical Requirement:** This module must work in complete isolation without any integration into the main app. It will be integrated in Stage 2.

______________________________________________________________________

## Deliverables

### 1. Core Module

**File:** `pikaraoke/lib/karaoke_database.py`

**Class:** `KaraokeDatabase`

**Public Methods:**

```python
class KaraokeDatabase:
    def __init__(self, db_path: str | None = None, backup_dir: str | None = None)
    def scan_library(self, songs_dir: str) -> dict[str, int]
    def create_backup_file(self) -> str | None
    def restore_from_file(self, uploaded_file_path: str) -> tuple[bool, str]
    def check_integrity(self) -> tuple[bool, str]
    def get_all_song_paths(self) -> list[str]
    def get_song_count(self) -> int
    def close(self)
```

### 2. Unit Tests

**File:** `tests/test_karaoke_database.py`

**Test Coverage:**

- Database initialization
- Schema creation and versioning
- File scanning (adds/moves/deletes/updates)
- CDG/ASS pairing logic
- Hash generation and collision handling
- Backup creation
- Restore functionality
- Integrity checking
- Edge cases (Unicode, permissions, corruption)

### 3. Documentation

- Inline docstrings for all public methods
- Usage examples in docstrings
- Error handling documentation

______________________________________________________________________

## Implementation Details

### Schema Design

```sql
-- Schema Version: 1
PRAGMA user_version = 1;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

-- Main songs table
CREATE TABLE IF NOT EXISTS songs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE NOT NULL,           -- Relative to songs_dir
    file_hash TEXT,                           -- SHA256: size + first 16KB
    filename TEXT NOT NULL,                   -- Basename only
    artist TEXT,                              -- Phase 4
    title TEXT,                               -- Parsed from filename
    variant TEXT,                             -- Phase 4
    year INTEGER,                             -- Phase 4
    genre TEXT,                               -- Phase 4
    youtube_id TEXT,                          -- Extracted from filename
    format TEXT NOT NULL,                     -- CDG/ZIP/MP4/MP4+ASS/MKV/etc.
    search_blob TEXT,                         -- Lowercase searchable text
    is_visible INTEGER DEFAULT 1,             -- Soft delete flag
    metadata_status TEXT DEFAULT 'pending',   -- pending/enriched/failed
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Performance indices
CREATE INDEX IF NOT EXISTS idx_file_hash ON songs(file_hash);
CREATE INDEX IF NOT EXISTS idx_metadata_status ON songs(metadata_status);
CREATE INDEX IF NOT EXISTS idx_artist ON songs(artist);
CREATE INDEX IF NOT EXISTS idx_title ON songs(title);
CREATE INDEX IF NOT EXISTS idx_search_blob ON songs(search_blob);
CREATE INDEX IF NOT EXISTS idx_is_visible ON songs(is_visible);

-- System metadata
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

### File Format Detection Logic

Based on existing `SongList.VALID_EXTENSIONS`:

```python
VALID_EXTENSIONS = {".mp4", ".mp3", ".zip", ".mkv", ".avi", ".webm", ".mov"}


def detect_format(file_path: str, files_in_dir: set[str]) -> str | None:
    """Detect song format with pairing logic.

    Args:
        file_path: Full path to the file
        files_in_dir: Set of lowercase filenames in same directory

    Returns:
        Format string or None if not a valid song
    """
    base, ext = os.path.splitext(file_path)
    basename = os.path.basename(base)
    ext = ext.lower()

    if ext not in VALID_EXTENSIONS:
        return None

    # CDG pairing: MP3 + CDG
    if ext == ".mp3" and (basename.lower() + ".cdg") in files_in_dir:
        return "CDG"

    # ZIP archives (assume CDG content)
    elif ext == ".zip":
        return "ZIP"

    # Video with subtitle pairing
    elif ext in [".mp4", ".mkv", ".avi", ".webm", ".mov"]:
        if (basename.lower() + ".ass") in files_in_dir:
            return ext[1:].upper() + "+ASS"  # MP4+ASS, MKV+ASS, etc.
        else:
            return ext[1:].upper()  # MP4, MKV, etc.

    # Standalone MP3 (no CDG pair)
    elif ext == ".mp3":
        return "MP3"

    return None
```

**Important:** Only the primary file (e.g., `.mp3` from CDG pair) should be added to the database. The `.cdg` file is detected for format classification but not stored separately.

### Hash Generation

**Algorithm:** SHA256 of (file_size + first 16KB)

**Rationale:**

- SHA256 is cryptographically stronger than MD5 (lower collision risk)
- Reading only first 16KB is fast even for large video files
- File size prevents same-content-different-size collisions
- This can detect file moves/renames even if filename changes

```python
import hashlib


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
            header = f.read(16384)  # 16KB

        hasher = hashlib.sha256()
        hasher.update(str(stats.st_size).encode("utf-8"))
        hasher.update(header)
        return hasher.hexdigest()
    except Exception as e:
        logging.warning(f"Failed to generate hash for {file_path}: {e}")
        return None
```

### Scan Library Algorithm (Fixed)

**Goal:** Synchronize database with disk state, detecting:

- New files (additions)
- Moved/renamed files (hash match)
- Deleted files (missing from disk)
- Updated files (hash changed)

**Pseudocode:**

```python
def scan_library(self, songs_dir: str) -> dict[str, int]:
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

    common_paths = disk_paths & db_paths  # Exists in both
    new_paths = disk_paths - db_paths  # On disk but not in DB
    missing_paths = db_paths - disk_paths  # In DB but not on disk

    # 4. Update existing files (check for content changes)
    for path in common_paths:
        disk_filename, disk_format, disk_hash = disk_files[path]
        db_row = db_rows[path]

        if disk_hash != db_row["file_hash"] or disk_format != db_row["format"]:
            update_song(db_row["id"], hash=disk_hash, format=disk_format, ...)
            stats["updated"] += 1

    # 5. Handle missing files (detect moves vs deletes)
    missing_by_hash = {
        db_rows[p]["file_hash"]: db_rows[p]
        for p in missing_paths
        if db_rows[p]["file_hash"]  # Only files with valid hashes
    }

    moved_paths = set()  # Track which new paths are actually moves

    for new_path in new_paths:
        new_filename, new_format, new_hash = disk_files[new_path]

        # Check if this "new" file is actually a moved file
        if new_hash and new_hash in missing_by_hash:
            old_row = missing_by_hash[new_hash]
            # UPDATE: Change path to new location
            update_song(old_row["id"], file_path=new_path, filename=new_filename, ...)
            moved_paths.add(new_path)
            del missing_by_hash[new_hash]  # Remove from missing (found it!)
            stats["moved"] += 1
        else:
            # Truly new file
            insert_song(new_path, new_filename, new_format, new_hash)
            stats["added"] += 1

    # 6. Delete truly missing files (weren't moved)
    for hash, row in missing_by_hash.items():
        delete_song(row["id"])
        stats["deleted"] += 1

    # Also delete files that had no hash (couldn't be matched)
    for path in missing_paths:
        if db_rows[path]["file_hash"] is None:
            delete_song(db_rows[path]["id"])
            stats["deleted"] += 1

    # 7. Update last scan timestamp
    update_metadata("last_scan", datetime.now().isoformat())

    commit()
    return stats  # {'added': X, 'moved': Y, 'deleted': Z, 'updated': W}
```

**Key Fixes from Reference Implementation:**

1. Properly handles files without hashes (don't leave orphaned)
2. Tracks which new paths are moves (prevents double-counting)
3. Deletes unmoved missing files
4. Uses SHA256 instead of MD5

### Search Blob Population

**Purpose:** Fast full-text search without complex parsing.

**Content:** Lowercase combination of:

- Filename (without extension)
- Title (parsed or original filename)
- Artist (if available)
- YouTube ID (if present)

```python
def build_search_blob(
    filename: str,
    title: str | None = None,
    artist: str | None = None,
    youtube_id: str | None = None,
) -> str:
    """Build searchable text blob for full-text search."""
    parts = []

    # Filename without extension
    clean_name = os.path.splitext(filename)[0].replace("_", " ")
    parts.append(clean_name)

    # Title (if different from filename)
    if title and title != clean_name:
        parts.append(title)

    # Artist
    if artist:
        parts.append(artist)

    # YouTube ID (for ID-based search)
    if youtube_id:
        parts.append(youtube_id)

    return " ".join(parts).lower()
```

**Usage:**

```sql
-- Fast search across all metadata
SELECT * FROM songs WHERE search_blob LIKE '%karaoke%' AND is_visible = 1;
```

### Backup & Restore

#### Create Backup

**Method:** SQLite Backup API (safe for live databases)

```python
def create_backup_file(self) -> str | None:
    """Create a snapshot of the database.

    Returns:
        Path to backup file or None on error
    """
    try:
        # Ensure backup directory exists
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)

        # Generate timestamped filename
        timestamp = datetime.now().strftime("pikaraoke_backup_%Y%m%d_%H%M%S.db")
        backup_path = os.path.join(self.backup_dir, timestamp)

        # Use SQLite backup API (safe during writes)
        backup_conn = sqlite3.connect(backup_path)
        self.conn.backup(backup_conn)
        backup_conn.close()

        logging.info(f"Backup created: {backup_path}")
        return backup_path
    except Exception as e:
        logging.error(f"Backup creation failed: {e}")
        return None
```

#### Restore from Backup

**Method:** File swap with safety checks

```python
def restore_from_file(self, uploaded_file_path: str) -> tuple[bool, str]:
    """Restore database from uploaded backup.

    Args:
        uploaded_file_path: Path to uploaded .db file

    Returns:
        (success: bool, message: str)
    """
    # 1. Validate file exists
    if not os.path.exists(uploaded_file_path):
        return False, "Upload file not found"

    # 2. Validate SQLite format
    try:
        with open(uploaded_file_path, "rb") as f:
            header = f.read(16)
        if b"SQLite format 3" not in header:
            return False, "Invalid file format. Not a SQLite database."
    except Exception as e:
        return False, f"File validation error: {e}"

    # 3. Validate schema compatibility (optional but recommended)
    try:
        test_conn = sqlite3.connect(uploaded_file_path)
        version = test_conn.execute("PRAGMA user_version").fetchone()[0]
        test_conn.close()

        if version != DB_VERSION:
            return (
                False,
                f"Incompatible database version: {version} (expected {DB_VERSION})",
            )
    except Exception as e:
        return False, f"Schema validation error: {e}"

    try:
        # 4. Close existing connection
        if self.conn:
            self.conn.close()

        # 5. Clean up old DB artifacts
        for ext in ["", "-wal", "-shm"]:
            target = self.db_path + ext
            if os.path.exists(target):
                try:
                    os.remove(target)
                except OSError as e:
                    logging.warning(f"Failed to remove {target}: {e}")

        # 6. Copy new file into place
        shutil.copy2(uploaded_file_path, self.db_path)

        # 7. Reconnect
        self._connect()

        logging.info("Database restored successfully")
        return True, "Restore successful. Database updated."

    except Exception as e:
        # Attempt to reconnect to old DB if restore failed
        try:
            self._connect()
        except:
            pass

        logging.error(f"Restore failed: {e}")
        return False, f"Restore failed: {e}"
```

### Integrity Check

```python
def check_integrity(self) -> tuple[bool, str]:
    """Validate database integrity.

    Returns:
        (is_valid: bool, message: str)
    """
    try:
        # SQLite built-in integrity check
        result = self.conn.execute("PRAGMA integrity_check").fetchone()[0]

        if result == "ok":
            return True, "Database integrity: OK"
        else:
            return False, f"Database integrity issues: {result}"

    except Exception as e:
        return False, f"Integrity check failed: {e}"
```

### Helper Methods

```python
def get_all_song_paths(self) -> list[str]:
    """Get list of all song file paths.

    Returns:
        List of file paths (sorted by filename)
    """
    cursor = self.conn.execute(
        "SELECT file_path FROM songs WHERE is_visible = 1 ORDER BY filename"
    )
    return [row[0] for row in cursor.fetchall()]


def get_song_count(self) -> int:
    """Get total number of songs in database.

    Returns:
        Count of visible songs
    """
    cursor = self.conn.execute("SELECT COUNT(*) FROM songs WHERE is_visible = 1")
    return cursor.fetchone()[0]


def close(self):
    """Close database connection gracefully."""
    if self.conn:
        self.conn.close()
        self.conn = None
```

______________________________________________________________________

## Testing Plan

### Unit Test Cases

**File:** `tests/test_karaoke_database.py`

```python
import pytest
import tempfile
import os
from pikaraoke.lib.karaoke_database import KaraokeDatabase


class TestKaraokeDatabase:

    def test_initialization(self):
        """Test database initialization with default paths."""
        # Should use get_data_directory() by default

    def test_schema_creation(self):
        """Test that schema is created correctly."""
        # Verify all tables and indices exist

    def test_scan_empty_directory(self):
        """Test scanning an empty directory."""
        # Should return stats with all zeros

    def test_scan_adds_files(self):
        """Test detecting new files."""
        # Add files, scan, verify added count

    def test_scan_detects_moves(self):
        """Test move detection via hash matching."""
        # Add file, scan, move file, scan again
        # Should show 1 moved, 0 added, 0 deleted

    def test_scan_detects_deletes(self):
        """Test detecting deleted files."""
        # Add file, scan, delete file, scan again
        # Should show 1 deleted

    def test_scan_detects_updates(self):
        """Test detecting file content changes."""
        # Add file, scan, modify file, scan again
        # Should show 1 updated

    def test_cdg_pairing(self):
        """Test CDG format detection."""
        # Create song.mp3 + song.cdg
        # Should detect as 'CDG' format, only add .mp3

    def test_ass_subtitle_pairing(self):
        """Test subtitle pairing."""
        # Create video.mp4 + video.ass
        # Should detect as 'MP4+ASS' format

    def test_unicode_filenames(self):
        """Test handling of Unicode filenames."""
        # Test Japanese, emoji, special characters

    def test_backup_creation(self):
        """Test backup file creation."""
        # Verify backup file is valid SQLite

    def test_restore_from_backup(self):
        """Test restore functionality."""
        # Create DB, backup, modify, restore, verify

    def test_restore_invalid_file(self):
        """Test restore with invalid file."""
        # Should reject non-SQLite files

    def test_integrity_check_valid(self):
        """Test integrity check on valid database."""
        # Should return True

    def test_integrity_check_corrupted(self):
        """Test integrity check on corrupted database."""
        # Manually corrupt DB, should return False

    def test_get_all_song_paths(self):
        """Test retrieving all song paths."""
        # Verify ordering and filtering

    def test_get_song_count(self):
        """Test song counting."""
        # Verify accuracy
```

### Edge Cases to Test

01. **Empty directory** - Should handle gracefully
02. **Permission errors** - Files that can't be read
03. **Symlinks** - Should follow or ignore?
04. **Hidden files** - Should ignore (starts with '.')
05. **Large files** - Ensure hash generation is fast
06. **Hash collisions** - Extremely rare but should not crash
07. **Concurrent access** - WAL mode should handle this
08. **Database file deletion** - Should recreate on next init
09. **Partial scan** - What if scan interrupted?
10. **Unicode edge cases** - Emoji in filenames, etc.

______________________________________________________________________

## Success Criteria Checklist

- \[ \] Database initializes with correct schema
- \[ \] WAL mode is enabled
- \[ \] `scan_library()` returns accurate stats
- \[ \] New files are added correctly
- \[ \] Moved files are detected (not deleted+added)
- \[ \] Deleted files are removed from DB
- \[ \] CDG pairs are detected and stored as single entry
- \[ \] ASS subtitles are detected and format updated
- \[ \] Hash generation is fast (\< 50ms per file)
- \[ \] Backup files are valid and can be opened
- \[ \] Restore operation swaps database safely
- \[ \] Integrity check validates database health
- \[ \] All unit tests pass
- \[ \] No memory leaks or unclosed connections
- \[ \] Handles Unicode filenames correctly
- \[ \] Gracefully handles permission errors

______________________________________________________________________

## Error Handling

All public methods should:

1. **Never crash the app** - Catch exceptions and return error states
2. **Log errors** - Use Python logging module
3. **Return meaningful messages** - Help users understand what went wrong
4. **Fail safely** - Prefer read-only mode over corruption

**Example:**

```python
def scan_library(self, songs_dir: str) -> dict[str, int]:
    """Scan library and sync database.

    Returns:
        Stats dict with keys: added, moved, deleted, updated
        On error, returns dict with all zeros and logs error
    """
    try:
        # ... implementation ...
    except Exception as e:
        logging.error(f"Scan failed: {e}")
        return {'added': 0, 'moved': 0, 'deleted': 0, 'updated': 0}
```

______________________________________________________________________

## Performance Considerations

### Expected Performance

| Library Size | Initial Scan | Subsequent Scan | Memory Usage |
|--------------|--------------|-----------------|--------------|
| 100 songs    | \< 2s         | \< 0.5s          | ~5 MB        |
| 1,000 songs  | \< 10s        | \< 2s            | ~10 MB       |
| 10,000 songs | \< 60s        | \< 10s           | ~50 MB       |

### Optimization Strategies

1. **Batch commits** - Commit every 100 inserts during scan
2. **Prepared statements** - Reuse compiled SQL
3. **Index usage** - Ensure queries use indices
4. **Lazy loading** - Don't load all rows into memory
5. **Hash caching** - Cache hashes to avoid recalculation

______________________________________________________________________

## Integration Preview (Stage 2)

**How this module will be used:**

```python
# In pikaraoke/karaoke.py

from pikaraoke.lib.karaoke_database import KaraokeDatabase

class Karaoke:
    def __init__(self, ...):
        # ... existing init code ...

        # Initialize database (Stage 2)
        self.db = KaraokeDatabase()

        # Scan library on startup
        stats = self.db.scan_library(self.download_path)
        logging.info(f"Library scan: {stats}")

        # Populate legacy SongList for backwards compat
        self.available_songs = SongList()
        self.available_songs.update(self.db.get_all_song_paths())
```

______________________________________________________________________

## Next Steps

After Stage 1 completion:

1. All unit tests pass
2. Code review completed
3. Performance benchmarks met
4. Documentation complete
5. Proceed to Stage 2 (App Integration)

______________________________________________________________________

**Document Status:** Ready for Implementation
**Last Updated:** 2026-01-09
**Approved By:** Pending
