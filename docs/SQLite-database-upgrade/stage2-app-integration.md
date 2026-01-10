# Stage 2: Read-Only Integration - Implementation Plan

**Stage:** 2 of 4
**Status:** Ready for Implementation (After Stage 1)
**Prerequisites:** Stage 1 (Core Database Layer Complete)
**Estimated Effort:** 0.5-1 day
**Risk Level:** Low

## Objective

Integrate `KaraokeDatabase` into PiKaraoke in read-only mode:

1. Database initialized on app startup
2. Library scanned and persisted across restarts
3. Existing `SongList` populated from database
4. All existing features work identically
5. No user-facing UI changes

**Critical Requirement:** Zero breaking changes. Users should not notice any difference.

## Coexistence Strategy

Both systems run in parallel during Stage 2:

```
Karaoke Application
├── KaraokeDB (New, Primary)
│   └── populates ↓
└── SongList (Legacy)
    └── All routes query this
```

**Why:** Validates database without risk. Easy rollback. No changes to routes/templates/queue.

## Files to Modify

### `pikaraoke/karaoke.py`

#### Before (Lines 299-301):

```python
# Initialize song list and load songs from download_path
self.available_songs = SongList()
self.get_available_songs()
```

#### After (Stage 2):

```python
from __future__ import annotations

from pikaraoke.lib.karaoke_database import KaraokeDatabase

# Initialize database
self.db = KaraokeDatabase()
logging.info("Database initialized")

# Scan library and sync with disk
stats = self.db.scan_library(self.download_path)
logging.info(
    f"Library scan: {stats['added']} added, {stats['moved']} moved, "
    f"{stats['deleted']} deleted, {stats['updated']} updated"
)

# Populate legacy SongList
self.available_songs = SongList()
self.available_songs.update(self.db.get_all_song_paths())
logging.info(f"Song list populated with {len(self.available_songs)} songs")
```

**Impact:**

- Startup: +2-10s on first run, +0.5-2s subsequent
- Memory: +5-50 MB
- Disk: Creates `~/.pikaraoke/pikaraoke.db` (1-5 KB per song)

#### Modify `get_available_songs()` (Lines 577-579)

**Before:**

```python
def get_available_songs(self) -> None:
    """Scan the download directory and update the available songs list."""
    self.available_songs.scan_directory(self.download_path)
```

**After:**

```python
from __future__ import annotations

import logging


def get_available_songs(self) -> None:
    """Scan directory and update song list.

    Stage 2: Syncs with database instead of direct scanning.
    """
    stats = self.db.scan_library(self.download_path)
    logging.info(f"Rescan stats: {stats}")

    self.available_songs.clear()
    self.available_songs.update(self.db.get_all_song_paths())
    logging.info(f"Song list refreshed with {len(self.available_songs)} songs")
```

**Note:** Existing `admin.refresh` route calls this, so "Rescan song directory" button uses database.

## Validation Checklist

### App Startup

- Database file created at `{get_data_directory()}/pikaraoke.db`
- WAL files created
- Scan completes and logs stats
- Startup time acceptable (\< previous + 10s)

### Browse/Search/Queue

- All songs displayed (same count as pre-migration)
- Songs sorted identically
- Pagination works
- Search works (filename/title)
- Queue operations work (add/skip/pause/reorder/remove)

### File Operations

- Delete song works
- Rename song works
- Download new song works
- "Rescan song directory" button works

## Test Scenarios

### Scenario 1: Fresh Install

1. Delete existing `pikaraoke.db`
2. Start app
3. Verify all songs scanned
4. Restart app
5. Verify songs persist (not rescanned)

### Scenario 2: File Changes While Running

1. Start app
2. Manually add song file
3. Click "Rescan song directory"
4. Verify new song appears

### Scenario 3: File Rename Detection

1. Start app (initial scan)
2. Restart app
3. Manually rename song file
4. Restart app
5. Verify: Song appears with new name (1 "moved", not 1 "deleted" + 1 "added")

### Scenario 4: File Deletion

1. Start app
2. Delete song file
3. Restart app
4. Verify: Song removed (1 "deleted")

### Scenario 5: CDG Pairing

1. Add `song.mp3` + `song.cdg`
2. Rescan
3. Verify: Only 1 entry (the .mp3), format = 'CDG'
4. Delete `song.mp3`
5. Verify: Entry removed, orphaned .cdg ignored

## Performance Benchmarks

| Metric                   | Target      |
| ------------------------ | ----------- |
| Startup (100 songs)      | \< 5s        |
| Startup (1000 songs)     | \< 15s       |
| Browse page load         | \< 1s        |
| Search response          | \< 500ms     |
| Rescan (no changes)      | \< 2s        |
| Memory usage increase    | \< 50MB      |

**Measurement:**

```python
from __future__ import annotations

import time

start = time.time()
stats = self.db.scan_library(self.download_path)
elapsed = time.time() - start
logging.info(f"Scan completed in {elapsed:.2f}s")
```

## Error Handling Tests

1. **Corrupted Database:** Logs error, recreates database, scans from scratch
2. **Permission Denied:** Logs warning, skips file, continues
3. **Invalid Format:** File ignored (not in VALID_EXTENSIONS)
4. **Database Locked:** Handles gracefully (WAL mode prevents this)
5. **Disk Full:** Logs error, continues with existing data

## Rollback Procedure

### Quick Rollback

```bash
git checkout HEAD~1 pikaraoke/karaoke.py
```

Restart app (uses old SongList-only approach).

### Delete Database (Optional)

```bash
# Linux/Mac
rm ~/.pikaraoke/pikaraoke.db*

# Windows
del %APPDATA%\pikaraoke\pikaraoke.db*
```

## Logging Strategy

```python
from __future__ import annotations

import time

logging.info("=" * 60)
logging.info("DATABASE INITIALIZATION - STAGE 2")
logging.info("=" * 60)
logging.info(f"Database path: {self.db.db_path}")
logging.info(f"Songs directory: {self.download_path}")

start_time = time.time()
stats = self.db.scan_library(self.download_path)
elapsed = time.time() - start_time

logging.info(f"Scan completed in {elapsed:.2f}s")
logging.info(f"  Added: {stats['added']}")
logging.info(f"  Moved: {stats['moved']}")
logging.info(f"  Deleted: {stats['deleted']}")
logging.info(f"  Updated: {stats['updated']}")
logging.info(f"Total songs: {self.db.get_song_count()}")
logging.info("=" * 60)
```

## Success Criteria

### Functional Requirements

- App starts without errors
- Database file created correctly
- All songs scanned on first run
- Songs persist across restarts
- Browse/search/queue work
- File operations work
- "Rescan" works
- Move detection works (not delete+add)
- CDG pairing works

### Performance Requirements

- Startup time acceptable
- No memory leaks
- Database size reasonable
- Browse/search responsive

### Quality Requirements

- No user-facing changes
- No breaking changes
- Existing tests pass
- Error handling graceful
- Logging informative

## Next Steps

After Stage 2 completion:

1. All validation tests pass
2. Performance benchmarks met
3. User acceptance testing complete
4. Proceed to Stage 3 (Admin UI)

In Stage 3, database features exposed in admin UI: Synchronize Library, Download Backup, Restore from Backup.

**Document Status:** Ready for Implementation (After Stage 1)
**Last Updated:** 2026-01-11
