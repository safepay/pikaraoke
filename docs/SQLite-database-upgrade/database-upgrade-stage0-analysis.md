# Database Upgrade to SQLite - STAGE 0 Analysis

**Date:** 2026-01-09
**Status:** ✅ COMPLETE
**Next Stage:** STAGE 1 - Core Database & Sync Implementation

______________________________________________________________________

## Overview

This document captures the analysis and planning phase (STAGE 0) for upgrading PiKaraoke from in-memory file scanning to a persistent SQLite database with content fingerprinting, backup/restore capabilities, and improved library management.

______________________________________________________________________

## 1. Database Class Location Decision

**Recommended location:** `pikaraoke/lib/db.py`

### Rationale:

- The `pikaraoke/lib/` directory contains all modular components:
  - `youtube_dl.py` - YouTube download utilities
  - `download_manager.py` - Download queue management
  - `song_list.py` - Current song list implementation
  - `file_resolver.py` - File handling utilities
  - `get_platform.py` - Platform detection
  - etc.
- Placing `db.py` here follows the existing architectural pattern
- Import pattern: `from pikaraoke.lib.db import KaraokeDB`
- Consistent with other library module organization

______________________________________________________________________

## 2. Current Scan Implementation Analysis

### Entry Point

**File:** `pikaraoke/karaoke.py:299-301`

```python
# Initialize song list and load songs from download_path
self.available_songs = SongList()
self.get_available_songs()
```

The `get_available_songs()` method (line 577-579) calls:

```python
def get_available_songs(self) -> None:
    """Scan the download directory and update the available songs list."""
    self.available_songs.scan_directory(self.download_path)
```

### SongList Implementation

**File:** `pikaraoke/lib/song_list.py`

**Current behavior:**

- Uses `Path.rglob("*.*")` to recursively find all files (lines 129-148)
- Validates file extensions: `.mp4, .mp3, .zip, .mkv, .avi, .webm, .mov`
- **In-memory only** - all data lost on restart
- **No persistence** - rescans entire directory tree on every startup
- **No rename/move detection** - treats moved files as deletion + new addition
- **No CDG pairing logic** - treats `.mp3` files as standalone songs
- Uses a hybrid set/list data structure for O(1) membership checks
- Maintains sorted cache for iteration and display

**Key methods:**

- `scan_directory(directory)` - Scans and replaces entire song list
- `add(song_path)` - Adds a song to the in-memory set
- `remove(song_path)` - Removes a song from the in-memory set
- `rename(old_path, new_path)` - Updates path after file rename
- `is_valid_song(file_path)` - Validates file extension

**Performance characteristics:**

- Membership check: O(1) average
- Add/Remove: O(1) average
- Iteration: O(n log n) on first access after modification
- Full scan: O(n) where n = total files in directory tree

______________________________________________________________________

## 3. Storage Locations Plan

### Platform-Aware Paths

Using the existing `get_data_directory()` function from `pikaraoke/lib/get_platform.py:138-162`:

```python
def get_data_directory() -> str:
    """Get the writable data directory for the application."""
    if is_windows():
        # Windows: %APPDATA%/pikaraoke
        base_path = os.environ.get("APPDATA")
        if not base_path:
            base_path = os.path.expanduser("~")
        path = os.path.join(base_path, "pikaraoke")
    else:
        # Linux, macOS, Android, Raspberry Pi: ~/.pikaraoke
        path = os.path.expanduser("~/.pikaraoke")

    # Ensure the directory exists
    if not os.path.exists(path):
        os.makedirs(path)

    return path
```

### Proposed Directory Structure

**Windows:** `%APPDATA%\pikaraoke\` (e.g., `C:\Users\Richard\AppData\Roaming\pikaraoke`)
**Linux/macOS/Pi:** `~/.pikaraoke/`

```
~/.pikaraoke/                      # Or %APPDATA%\pikaraoke on Windows
├── pikaraoke.db                   # Main SQLite database file
├── pikaraoke.db-wal               # Write-Ahead Log (auto-created by SQLite)
├── pikaraoke.db-shm               # Shared memory file (auto-created by SQLite)
├── backups/                       # Temporary storage for backup downloads
│   ├── pikaraoke_backup_20260109_143022.db
│   └── pikaraoke_backup_20260109_150000.db
├── config.ini                     # ✅ Already uses this location
└── qrcode.png                     # ✅ Already uses this location
```

### File Specifications

**Database File:**

- **Path:** `{get_data_directory()}/pikaraoke.db`
- **Format:** SQLite 3 with WAL mode enabled
- **Permissions:** User read/write only
- **Size:** Approximately 1-5 KB per song (varies with metadata)

**Backup Directory:**

- **Path:** `{get_data_directory()}/backups/`
- **Purpose:** Temporary storage for user-downloadable backup files
- **Cleanup:** Old backups can be purged after download or on startup
- **Filename Format:** `pikaraoke_backup_YYYYMMDD_HHMMSS.db`

______________________________________________________________________

## 4. Issues Found in Reference Implementation

### File: `database_upgrade.py` (Reference Implementation)

#### 🔴 CRITICAL BUG #1: Incomplete Deletion Logic (Lines 238-245)

```python
# C. Delete whatever is still missing
for remaining_hash in missing_hashes:
    self.conn.execute(
        "DELETE FROM songs WHERE id=?", (missing_hashes[remaining_hash]["id"],)
    )
    stats["deleted"] += 1

# D. Clean up path-based missing files
for path in missing_files:
    pass  # ← EMPTY LOOP - LEFTOVER DEBUG CODE
```

**Problem:**

- Only deletes files that had valid hashes AND were matched to moved files
- Files without hashes (corrupted, unreadable) in `missing_files` are **never deleted** from DB
- The empty loop on line 244 suggests incomplete implementation

**Fix Required:**

```python
# C. Delete hash-matched files that couldn't be found
for remaining_hash, row in missing_hashes.items():
    self.conn.execute("DELETE FROM songs WHERE id=?", (row["id"],))
    stats["deleted"] += 1

# D. Delete path-based missing files that weren't matched by hash
for path in missing_files:
    if path not in moved_paths:  # Skip paths that were already moved
        row = db_rows[path]
        self.conn.execute("DELETE FROM songs WHERE id=?", (row["id"],))
        stats["deleted"] += 1
```

#### 🔴 CRITICAL BUG #2: No CDG Cleanup

**Problem:**
The deletion logic doesn't handle CDG paired files. When a `.mp3` file is deleted:

- The `.cdg` file remains in the database as an orphan
- The CDG file can't be played without its audio partner
- Database becomes inconsistent with playable content

**Current Detection Logic (Lines 188-191):**

```python
# Pair Detection Logic
if ext == ".mp3" and (base.lower() + ".cdg") in files_lower:
    fmt = "CDG"
elif ext == ".zip":
    fmt = "ZIP"
elif ext in [".mp4", ".mkv", ".avi", ".webm"]:
    fmt = "MP4+ASS" if (base.lower() + ".ass") in files_lower else "MP4"
```

**Fix Required:**

- Store both `.mp3` and `.cdg` paths in database (or mark CDG as non-primary)
- When deleting CDG format, remove both files from DB
- When scanning, only add the primary file (`.mp3`) as the playable song

#### 🔴 CRITICAL BUG #3: Hash Collision Edge Case

**Problem (Line 228-232):**

```python
if fp and fp in missing_hashes:
    old_row = missing_hashes[fp]
    self.conn.execute(
        "UPDATE songs SET file_path=?, filename=?, format=? WHERE id=?",
        (path, filename, fmt, old_row["id"]),
    )
    del missing_hashes[fp]  # Mark as handled
```

If two different files produce the same hash (extremely rare but theoretically possible with MD5 of size+header), the code will:

- Incorrectly match the new file to the wrong old file
- Lose track of one of the files

**Fix:** Use SHA256 instead of MD5, or add file size as a secondary check.

#### ⚠️ DESIGN ISSUE #1: Missing Search Index Population

**Line 74:**

```python
search_blob TEXT,
```

The `search_blob` field is defined but **never populated** in the codebase.

**Purpose:** Should contain lowercase searchable text combining artist, title, filename for fast full-text search.

**Fix Required:**

```python
def add_song_placeholder(self, path, filename, fmt, fp):
    """Inserts basic record. Metadata enrichment happens in Phase 2."""
    clean = os.path.splitext(filename)[0].replace("_", " ")
    # Build searchable blob
    search_text = f"{clean} {filename}".lower()

    self.conn.execute(
        """
        INSERT INTO songs (file_path, file_hash, filename, title, format,
                          metadata_status, search_blob)
        VALUES (?, ?, ?, ?, ?, 'pending', ?)
    """,
        (path, fp, filename, clean, fmt, search_text),
    )
```

#### ⚠️ DESIGN ISSUE #2: Missing Search Indices

The schema creates indices for:

- `file_hash` (line 79)
- `metadata_status` (line 80)

But **missing critical indices** for:

- `artist` - needed for "browse by artist" queries
- `title` - needed for "browse by title" queries
- `search_blob` - needed for full-text search

**Fix Required:**

```sql
CREATE INDEX IF NOT EXISTS idx_artist ON songs(artist);
CREATE INDEX IF NOT EXISTS idx_title ON songs(title);
CREATE INDEX IF NOT EXISTS idx_search_blob ON songs(search_blob);
CREATE INDEX IF NOT EXISTS idx_is_visible ON songs(is_visible);
```

#### ⚠️ DESIGN ISSUE #3: Platform Path Compatibility

**Lines 37-39:**

```python
def __init__(self, db_path, backup_dir):
    self.db_path = db_path
    self.backup_dir = backup_dir
```

The constructor accepts arbitrary paths, but should enforce platform-aware defaults using `get_data_directory()`.

**Fix Required:**

```python
from pikaraoke.lib.get_platform import get_data_directory


def __init__(self, db_path=None, backup_dir=None):
    if db_path is None:
        data_dir = get_data_directory()
        db_path = os.path.join(data_dir, "pikaraoke.db")
    if backup_dir is None:
        data_dir = get_data_directory()
        backup_dir = os.path.join(data_dir, "backups")

    self.db_path = db_path
    self.backup_dir = backup_dir
```

#### ⚠️ DESIGN ISSUE #4: No Last Scanned Timestamp

The schema doesn't track when the library was last synchronized. This makes it difficult to:

- Show users when the library was last updated
- Implement automatic re-scanning after N days
- Debug sync issues

**Fix Required:**
Add a metadata table:

```sql
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

Update on each scan:

```python
self.conn.execute(
    "INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_scan', ?)",
    (datetime.now().isoformat(),),
)
```

______________________________________________________________________

## 5. Admin UI Location Analysis

### Current "Refresh Song List" Implementation

**File:** `pikaraoke/templates/info.html:410-424`

```html
<div class="card">
    <header class="card-header py-3 px-5 collapsible-header is-collapsed">
        <h3 class="title mb-0">{% trans %}Refresh the song list{% endtrans %}</h3>
    </header>
    <div class="card-content collapsible-content">
        <div class="content">
            <p class="">{% trans -%}
                You should only need to do this if you manually copied files to the
                download directory while pikaraoke was running.
            {%- endtrans %}</p>
            <a class="button is-primary is-inverted"
               href="{{ url_for('admin.refresh') }}"
            >{% trans %}Rescan song directory{% endtrans %}</a>
        </div>
    </div>
</div>
```

**Current Location:** Under the "Updates" section heading (line 406)

**Current Behavior:**

- Collapses by default (`is-collapsed`)
- Links to `admin.refresh` route
- Simple explanation text + single button

### Proposed Changes for STAGE 3

**New Section Title:** "Manage Song Library"

**Features to Add:**

1. **Synchronize Library** button (replaces "Rescan song directory")

   - Calls `db.scan_library()` to detect adds/moves/deletes
   - Shows stats: "X added, Y moved, Z deleted"

2. **Download Database Backup** button

   - Calls `db.create_backup_file()`
   - Serves file via Flask's `send_file()`

3. **Restore Database from Backup** file upload

   - File input + submit button
   - Confirmation dialog with warning
   - Calls `db.restore_from_file()`
   - Requires app restart/reload

**Visual Layout:**

```
┌─────────────────────────────────────────────────┐
│ ▼ Manage Song Library                          │
├─────────────────────────────────────────────────┤
│                                                 │
│ Synchronize Library                            │
│ ───────────────────────────────────────────     │
│ Scan for new, moved, or deleted files on disk. │
│ [Synchronize Library]                          │
│                                                 │
│ ─────────────────────────────────────────────   │
│                                                 │
│ Backup & Restore                               │
│ ───────────────────────────────────────────     │
│ Download a backup of your song database.       │
│ [Download Database Backup]                     │
│                                                 │
│ Restore from a backup file:                    │
│ [Choose File] [Restore Database]               │
│ ⚠ This will overwrite your current library.    │
│                                                 │
└─────────────────────────────────────────────────┘
```

______________________________________________________________________

## 6. Integration Strategy

### Phase 1: Coexistence Period (STAGES 1-2)

During initial rollout, both systems will coexist:

**`Karaoke.__init__()` modification (around line 300):**

```python
# Initialize song list (legacy - keep for now)
self.available_songs = SongList()

# Initialize database (new)
from pikaraoke.lib.db import KaraokeDB

self.db = KaraokeDB()
self.db.scan_library(self.download_path)

# Populate legacy SongList from database for backwards compatibility
self.available_songs.update(self.db.get_all_song_paths())
```

**Benefits:**

- Zero breaking changes to existing code
- All existing search/browse/queue logic continues to work
- Database runs in background, validating accuracy
- Easy rollback if issues discovered

### Phase 2: Database-First (STAGE 3+)

Once validated, switch to database as primary source:

```python
# Remove SongList initialization
# self.available_songs = SongList()

# Database is now primary
from pikaraoke.lib.db import KaraokeDB

self.db = KaraokeDB()
self.db.scan_library(self.download_path)
```

Update browse/search routes to query database directly.

______________________________________________________________________

## 7. File Format Support Matrix

### Currently Supported (SongList)

| Extension | Format Name | Playback Support |
|-----------|-------------|------------------|
| `.mp4`    | Standalone  | ✅ Video + Audio |
| `.mp3`    | Standalone  | ✅ Audio only    |
| `.zip`    | ZIP         | ✅ CDG Archive   |
| `.mkv`    | Standalone  | ✅ Video + Audio |
| `.avi`    | Standalone  | ✅ Video + Audio |
| `.webm`   | Standalone  | ✅ Video + Audio |
| `.mov`    | Standalone  | ✅ Video + Audio |

### To Support with Database (Enhanced Detection)

| Primary File | Pair File | Format Name | Detection Logic |
|-------------|-----------|-------------|-----------------|
| `.mp3`      | `.cdg`    | `CDG`       | Check if `{basename}.cdg` exists (case-insensitive) |
| `.zip`      | N/A       | `ZIP`       | Assume contains CDG archive |
| `.mp4`      | `.ass`    | `MP4+ASS`   | Check if `{basename}.ass` subtitle exists |
| `.mp4`      | N/A       | `MP4`       | Standalone video |
| `.mkv`      | `.ass`    | `MKV+ASS`   | Check if `{basename}.ass` subtitle exists |
| `.mkv`      | N/A       | `MKV`       | Standalone video |

**Note:** Only the **primary file** should appear in song lists. The pair file is tracked for cleanup purposes only.

______________________________________________________________________

## 8. Database Schema (Final)

```sql
-- Schema Version: 1
PRAGMA user_version = 1;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

-- Main songs table
CREATE TABLE IF NOT EXISTS songs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE NOT NULL,           -- Relative path from download_dir
    file_hash TEXT,                           -- SHA256 of size + first 16KB
    filename TEXT NOT NULL,                   -- Just the filename (no path)
    artist TEXT,                              -- Parsed or enriched
    title TEXT,                               -- Parsed or enriched
    variant TEXT,                             -- e.g., "Acoustic", "Live"
    year INTEGER,                             -- Release year (from metadata)
    genre TEXT,                               -- Musical genre
    youtube_id TEXT,                          -- Extracted from filename
    format TEXT NOT NULL,                     -- CDG, ZIP, MP4, MP4+ASS, etc.
    search_blob TEXT,                         -- Lowercase searchable text
    is_visible INTEGER DEFAULT 1,             -- Hide without deleting
    metadata_status TEXT DEFAULT 'pending',   -- pending/enriched/failed
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Indices for performance
CREATE INDEX IF NOT EXISTS idx_file_hash ON songs(file_hash);
CREATE INDEX IF NOT EXISTS idx_metadata_status ON songs(metadata_status);
CREATE INDEX IF NOT EXISTS idx_artist ON songs(artist);
CREATE INDEX IF NOT EXISTS idx_title ON songs(title);
CREATE INDEX IF NOT EXISTS idx_search_blob ON songs(search_blob);
CREATE INDEX IF NOT EXISTS idx_is_visible ON songs(is_visible);

-- Metadata table for system info
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Track last scan time
INSERT OR REPLACE INTO metadata (key, value)
VALUES ('last_scan', CURRENT_TIMESTAMP);
```

______________________________________________________________________

## 9. Summary & Decisions

### ✅ Decisions Made

| Decision Point | Resolution |
|---------------|------------|
| **DB Location** | `pikaraoke/lib/db.py` |
| **DB File Path** | `{get_data_directory()}/pikaraoke.db` |
| **Backup Directory** | `{get_data_directory()}/backups/` |
| **Admin UI Location** | Modify "Updates" section in `info.html` |
| **Hash Algorithm** | SHA256 (more robust than MD5) |
| **Pairing Logic** | Detect CDG, ASS pairs; store only primary file |
| **Migration Strategy** | Coexistence → Gradual switchover |

### 🔧 Fixes to Implement in STAGE 1

1. ✅ Fix deletion logic to handle both hash-matched AND non-matched missing files
2. ✅ Add CDG/ASS cleanup when deleting paired files
3. ✅ Use `get_data_directory()` instead of hardcoded paths
4. ✅ Populate `search_blob` field for fast full-text search
5. ✅ Add proper indices for artist, title, search performance
6. ✅ Add `metadata` table with `last_scan` tracking
7. ✅ Upgrade hash to SHA256 for better collision resistance
8. ✅ Add timestamps (`created_at`, `updated_at`) to songs table

### 📋 Next Steps (STAGE 1)

1. Create `pikaraoke/lib/db.py` with fixed implementation
2. Implement `KaraokeDB` class with:
   - `scan_library(songs_dir)` - Full sync with disk
   - `create_backup_file()` - Export snapshot
   - `restore_from_file(path)` - Import snapshot
   - `check_integrity()` - Validate database health
3. Write unit tests for edge cases
4. Validate on test dataset

______________________________________________________________________

## 10. Risk Assessment

### Low Risk

- ✅ Database file location (uses existing `get_data_directory()`)
- ✅ Backup/restore (isolated feature, easy to test)
- ✅ Coexistence strategy (no breaking changes)

### Medium Risk

- ⚠️ File hash collisions (mitigated by SHA256)
- ⚠️ Unicode filename handling (Windows path encoding)
- ⚠️ Large library scan time (10K+ songs)

### Mitigation Strategies

- Use SHA256 instead of MD5 (lower collision probability)
- Test with international characters (Japanese, Korean, etc.)
- Add progress reporting for long scans
- Implement scan cancellation if needed

______________________________________________________________________

## Appendix A: Reference Files

| File | Lines | Purpose |
|------|-------|---------|
| `pikaraoke/karaoke.py` | 299-301 | Song list initialization |
| `pikaraoke/lib/song_list.py` | 129-148 | Current scan implementation |
| `pikaraoke/lib/get_platform.py` | 138-162 | Data directory utilities |
| `pikaraoke/templates/info.html` | 410-424 | Admin UI refresh section |
| `database_upgrade.py` | All | Reference implementation (with bugs) |

______________________________________________________________________

## Appendix B: Flask Route Structure

Based on template analysis:

```python
# Routes referenced in info.html
admin.refresh         → Rescan song directory
admin.update_ytdl     → Update yt-dlp
admin.quit            → Quit Pikaraoke
admin.reboot          → Reboot system (Pi/Linux only)
admin.shutdown        → Shutdown system (Pi/Linux only)
admin.expand_fs       → Expand filesystem (Pi only)
admin.login           → Admin login
admin.logout          → Admin logout
preferences.change_preferences → Update user preferences
images.qrcode         → Serve QR code image
```

**New routes needed for STAGE 3:**

- `admin.sync_library` → Synchronize database with disk
- `admin.download_backup` → Export database backup
- `admin.upload_backup` → Import database backup

______________________________________________________________________

**END OF STAGE 0 ANALYSIS**

**Status:** ✅ Ready to proceed to STAGE 1
**Approved:** Pending user confirmation
**Next Action:** Create `pikaraoke/lib/db.py` with all fixes applied
