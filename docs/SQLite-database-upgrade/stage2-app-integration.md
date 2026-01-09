# Stage 2: Read-Only Integration - Detailed Implementation Plan

**Stage:** 2 of 4
**Status:** 📋 Ready for Implementation (After Stage 1)
**Prerequisites:** Stage 1 (Core Database Layer Complete)
**Estimated Effort:** 0.5-1 day
**Risk Level:** Low

______________________________________________________________________

## Objective

Integrate the `KaraokeDatabase` class into the main PiKaraoke application in **read-only mode**, ensuring that:

1. Database is initialized on app startup
2. Library is scanned and persisted across restarts
3. Existing `SongList` is populated from database for backwards compatibility
4. All existing features work identically to pre-migration behavior
5. No changes to user-facing UI (yet)

**Critical Requirement:** This stage must introduce ZERO breaking changes. Users should not notice any difference in app behavior.

______________________________________________________________________

## Coexistence Strategy

During Stage 2, both systems will run in parallel:

```
┌─────────────────────────────────────────┐
│         Karaoke Application             │
├─────────────────────────────────────────┤
│                                         │
│  ┌──────────────┐    ┌──────────────┐  │
│  │ KaraokeDB    │    │  SongList    │  │
│  │ (New, Primary)    │  (Legacy)    │  │
│  └──────┬───────┘    └──────▲───────┘  │
│         │                   │           │
│         │  populate from    │           │
│         └───────────────────┘           │
│                                         │
│  All existing routes query SongList    │
│  (No changes to browse/search/queue)   │
│                                         │
└─────────────────────────────────────────┘
```

**Why This Approach?**

- Validates database accuracy without risk
- Easy rollback if issues discovered
- Allows gradual transition in future stages
- No changes to Flask routes, templates, or queue logic

______________________________________________________________________

## Files to Modify

### 1. `pikaraoke/karaoke.py`

**Section:** `__init__()` method (lines 95-320)

**Changes:**

#### Before (Current Code - Line 299-301):

```python
# Initialize song list and load songs from download_path
self.available_songs = SongList()
self.get_available_songs()
```

#### After (Stage 2 - Modified):

```python
# Initialize database (NEW - Stage 2)
from pikaraoke.lib.karaoke_database import KaraokeDatabase

self.db = KaraokeDatabase()  # Uses get_data_directory() by default
logging.info("Database initialized")

# Scan library and sync with disk
stats = self.db.scan_library(self.download_path)
logging.info(
    f"Library scan complete: {stats['added']} added, {stats['moved']} moved, "
    f"{stats['deleted']} deleted, {stats['updated']} updated"
)

# Initialize legacy SongList for backwards compatibility
self.available_songs = SongList()
self.available_songs.update(self.db.get_all_song_paths())
logging.info(f"Song list populated with {len(self.available_songs)} songs")
```

**Impact Analysis:**

- **Startup time:** +2-10 seconds on first run (initial scan)
- **Subsequent runs:** +0.5-2 seconds (database read + quick sync)
- **Memory:** +5-50 MB (database overhead, scales with library size)
- **Disk:** Creates `~/.pikaraoke/pikaraoke.db` (1-5 KB per song)

#### Modify `get_available_songs()` Method (Lines 577-579)

**Before:**

```python
def get_available_songs(self) -> None:
    """Scan the download directory and update the available songs list."""
    self.available_songs.scan_directory(self.download_path)
```

**After:**

```python
def get_available_songs(self) -> None:
    """Scan the download directory and update the available songs list.

    Stage 2: This now syncs with the database instead of scanning directly.
    """
    # Rescan library (detects changes made while app was running)
    stats = self.db.scan_library(self.download_path)
    logging.info(f"Rescan stats: {stats}")

    # Update legacy SongList from database
    self.available_songs.clear()
    self.available_songs.update(self.db.get_all_song_paths())
    logging.info(f"Song list refreshed with {len(self.available_songs)} songs")
```

**Note:** The existing `admin.refresh` route calls `get_available_songs()`, so this change makes the "Rescan song directory" button use the database.

______________________________________________________________________

## Validation Checklist

### Functional Validation

**Before declaring Stage 2 complete, verify:**

#### App Startup

- \[ \] App starts successfully without errors
- \[ \] Database file created at `{get_data_directory()}/pikaraoke.db`
- \[ \] WAL files (`pikaraoke.db-wal`, `pikaraoke.db-shm`) created
- \[ \] Scan completes and logs stats
- \[ \] Startup time is acceptable (\< previous + 10s)

#### Browse Page (`/files`)

- \[ \] All songs displayed (same count as pre-migration)
- \[ \] Songs sorted identically to before
- \[ \] Pagination works correctly
- \[ \] No missing songs
- \[ \] No duplicate entries

#### Search Page (`/search`)

- \[ \] Search by filename works
- \[ \] Search by title works
- \[ \] Search results match pre-migration behavior
- \[ \] No false positives or missing results

#### Queue Operations

- \[ \] Can add songs to queue
- \[ \] Queue displays correctly
- \[ \] Playback works identically
- \[ \] Can skip/pause/resume
- \[ \] Can reorder queue
- \[ \] Can remove from queue

#### File Operations

- \[ \] Delete song (via `/delete`) works
- \[ \] Rename song (via `/rename`) works
- \[ \] Download new song works

#### Admin Operations

- \[ \] "Rescan song directory" button works (calls `get_available_songs()`)
- \[ \] Shows updated count after rescan

### Data Validation

**Test Scenarios:**

#### Scenario 1: Fresh Install

1. Delete existing `pikaraoke.db` if present
2. Start app
3. Verify all songs scanned correctly
4. Restart app
5. Verify songs persist (loaded from DB, not rescanned)

#### Scenario 2: File Changes While App Running

1. Start app
2. Manually add a new song file to download directory
3. Click "Rescan song directory"
4. Verify new song appears in browse list

#### Scenario 3: File Rename Detection

1. Start app (initial scan)
2. Restart app
3. Manually rename a song file on disk
4. Restart app again
5. Verify: Song appears with new name (not deleted + re-added)
6. Verify: Database shows 1 "moved", not 1 "deleted" + 1 "added"

#### Scenario 4: File Deletion Detection

1. Start app
2. Manually delete a song file from disk
3. Restart app
4. Verify: Song no longer appears in browse list
5. Verify: Database shows 1 "deleted"

#### Scenario 5: CDG Pairing

1. Add `song.mp3` + `song.cdg` to download directory
2. Rescan
3. Verify: Only 1 entry in song list (the .mp3)
4. Verify: Format in database is 'CDG', not 'MP3'
5. Delete `song.mp3`
6. Verify: Entry removed from database
7. Verify: Orphaned `song.cdg` doesn't cause errors

### Performance Validation

**Benchmarks:**

| Metric | Target | Actual | Pass/Fail |
|--------|--------|--------|-----------|
| Startup time (100 songs) | \< 5s | \_\_\_\_\_ | ☐ |
| Startup time (1000 songs) | \< 15s | \_\_\_\_\_ | ☐ |
| Browse page load | \< 1s | \_\_\_\_\_ | ☐ |
| Search response | \< 500ms | \_\_\_\_\_ | ☐ |
| Rescan (no changes) | \< 2s | \_\_\_\_\_ | ☐ |
| Memory usage increase | \< 50MB | \_\_\_\_\_ | ☐ |

**How to measure:**

```python
# Add to Karaoke.__init__() for testing
import time

start = time.time()
stats = self.db.scan_library(self.download_path)
elapsed = time.time() - start
logging.info(f"Scan completed in {elapsed:.2f}s")
```

### Error Handling Validation

**Test Error Conditions:**

1. **Corrupted Database**

   - Manually corrupt `pikaraoke.db`
   - Start app
   - Expected: Logs error, recreates database, scans from scratch

2. **Permission Denied**

   - Make a song file unreadable (chmod 000)
   - Rescan
   - Expected: Logs warning, skips file, continues with others

3. **Invalid Song Format**

   - Add a `.txt` file to download directory
   - Rescan
   - Expected: File ignored (not in VALID_EXTENSIONS)

4. **Database File Locked**

   - Open `pikaraoke.db` in another process with exclusive lock
   - Try to start app
   - Expected: Handles gracefully (WAL mode should prevent this)

5. **Disk Full**

   - Fill disk to capacity
   - Try to rescan
   - Expected: Logs error, app continues with existing data

______________________________________________________________________

## Rollback Procedure

If critical issues are discovered during validation:

### Quick Rollback (Emergency)

**Step 1:** Revert `pikaraoke/karaoke.py` to previous version

```bash
git checkout HEAD~1 pikaraoke/karaoke.py
```

**Step 2:** Restart app

```bash
# App will use old SongList-only approach
```

**Step 3:** Optionally delete database file

```bash
# On Linux/Mac:
rm ~/.pikaraoke/pikaraoke.db*

# On Windows:
del %APPDATA%\pikaraoke\pikaraoke.db*
```

### Permanent Rollback (Abandon Stage 2)

**Step 1:** Remove database initialization code

```python
# In pikaraoke/karaoke.py, revert to:
self.available_songs = SongList()
self.get_available_songs()
```

**Step 2:** Remove import

```python
# Remove this line:
from pikaraoke.lib.karaoke_database import KaraokeDatabase
```

**Step 3:** Delete database module (optional)

```bash
rm pikaraoke/lib/karaoke_database.py
```

**Impact:** No data loss (database just stops being used, file scanning resumes)

______________________________________________________________________

## Edge Cases & Known Issues

### Edge Case 1: Very Large Libraries (10K+ songs)

**Symptom:** Initial scan takes > 60 seconds
**Impact:** Users may think app is frozen
**Mitigation:**

- Add progress logging every 100 files
- Consider background scanning with progress bar (future enhancement)
- Document expected startup time in release notes

### Edge Case 2: Network-Mounted Directories

**Symptom:** Slow file access, timeouts
**Impact:** Hash generation may be very slow
**Mitigation:**

- Add timeout to hash generation (skip if > 5s)
- Log warning about network storage performance
- Consider caching hashes more aggressively

### Edge Case 3: Symlinks

**Symptom:** Same file appears twice (once via real path, once via symlink)
**Current Behavior:** Both paths added as separate songs
**Future Fix:** Resolve symlinks to real paths before adding

### Edge Case 4: Case-Sensitive vs Case-Insensitive Filesystems

**Symptom:** On macOS (case-insensitive), `Song.mp3` and `song.mp3` are same file
**Current Behavior:** Database stores both paths but disk has only one
**Mitigation:** Normalize paths to lowercase on case-insensitive systems

______________________________________________________________________

## Logging Strategy

**Add informative logs for troubleshooting:**

```python
# In __init__()
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
logging.info(f"Total songs in database: {self.db.get_song_count()}")
logging.info("=" * 60)
```

**Expected Output:**

```
============================================================
DATABASE INITIALIZATION - STAGE 2
============================================================
Database path: /home/user/.pikaraoke/pikaraoke.db
Songs directory: /home/user/pikaraoke-songs
Scan completed in 3.47s
  Added: 247
  Moved: 0
  Deleted: 0
  Updated: 0
Total songs in database: 247
============================================================
```

______________________________________________________________________

## Testing Procedure

### Manual Testing Script

**Create a test script:** `test_stage2.sh` (Linux/Mac) or `test_stage2.bat` (Windows)

```bash
#!/bin/bash
# test_stage2.sh - Manual testing script for Stage 2

echo "=== Stage 2 Integration Test ==="

# Test 1: Fresh install
echo "[Test 1] Fresh install"
rm -f ~/.pikaraoke/pikaraoke.db*
python -m pikaraoke.app &
PID=$!
sleep 10
curl -s http://localhost:5555/files | grep -q "song" && echo "✓ Browse page works" || echo "✗ Browse page failed"
kill $PID

# Test 2: Persistence
echo "[Test 2] Database persistence"
python -m pikaraoke.app &
PID=$!
sleep 5
curl -s http://localhost:5555/files > /tmp/before.html
kill $PID

python -m pikaraoke.app &
PID=$!
sleep 5
curl -s http://localhost:5555/files > /tmp/after.html
kill $PID

diff /tmp/before.html /tmp/after.html && echo "✓ Songs persisted" || echo "✗ Songs changed after restart"

# Test 3: File changes detection
echo "[Test 3] File changes"
touch ~/pikaraoke-songs/new_test_song.mp4
python -m pikaraoke.app &
PID=$!
sleep 10
curl -s http://localhost:5555/admin/refresh
sleep 2
curl -s http://localhost:5555/files | grep -q "new_test_song" && echo "✓ New file detected" || echo "✗ New file not found"
kill $PID
rm ~/pikaraoke-songs/new_test_song.mp4

echo "=== Tests complete ==="
```

### Automated Testing

**Add integration test:** `tests/test_stage2_integration.py`

```python
import pytest
import tempfile
import os
from pikaraoke.karaoke import Karaoke


class TestStage2Integration:

    @pytest.fixture
    def temp_songs_dir(self):
        """Create temporary song directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def temp_data_dir(self):
        """Create temporary data directory for database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    def test_app_starts_with_database(self, temp_songs_dir, temp_data_dir):
        """Test that app initializes with database."""
        # Create a test song
        test_song = os.path.join(temp_songs_dir, "test.mp4")
        open(test_song, "w").close()

        # Initialize app (should create database)
        app = Karaoke(download_path=temp_songs_dir)

        # Verify database exists
        assert os.path.exists(app.db.db_path)

        # Verify song was scanned
        assert len(app.available_songs) == 1
        assert "test.mp4" in app.available_songs[0]

    def test_songs_persist_across_restarts(self, temp_songs_dir, temp_data_dir):
        """Test that songs are loaded from database on restart."""
        # First run: scan and populate
        test_song = os.path.join(temp_songs_dir, "test.mp4")
        open(test_song, "w").close()

        app1 = Karaoke(download_path=temp_songs_dir)
        count1 = len(app1.available_songs)
        db_path = app1.db.db_path
        app1.db.close()

        # Second run: should load from database (not rescan)
        app2 = Karaoke(download_path=temp_songs_dir)
        count2 = len(app2.available_songs)
        app2.db.close()

        # Counts should match
        assert count1 == count2 == 1

    def test_move_detection(self, temp_songs_dir, temp_data_dir):
        """Test that moved files are detected correctly."""
        # Create and scan initial file
        old_path = os.path.join(temp_songs_dir, "old_name.mp4")
        open(old_path, "w").close()

        app = Karaoke(download_path=temp_songs_dir)
        app.db.close()

        # Move file
        new_path = os.path.join(temp_songs_dir, "new_name.mp4")
        os.rename(old_path, new_path)

        # Rescan (should detect move)
        app2 = Karaoke(download_path=temp_songs_dir)
        stats = app2.db.scan_library(temp_songs_dir)

        # Verify moved (not deleted + added)
        assert stats["moved"] == 1
        assert stats["added"] == 0
        assert stats["deleted"] == 0
```

______________________________________________________________________

## Success Criteria Checklist

### Functional Requirements

- \[ \] App starts without errors
- \[ \] Database file created in correct location
- \[ \] All songs scanned on first run
- \[ \] Songs persist across restarts
- \[ \] Browse page shows all songs
- \[ \] Search functionality works
- \[ \] Queue operations work
- \[ \] File deletion works
- \[ \] File renaming works
- \[ \] "Rescan song directory" works
- \[ \] Move detection works (not delete+add)
- \[ \] CDG pairing works correctly

### Performance Requirements

- \[ \] Startup time acceptable (\< 15s for 1K songs)
- \[ \] No memory leaks
- \[ \] Database file size reasonable (\< 10 KB per song)
- \[ \] Browse page loads in \< 1s
- \[ \] Search responds in \< 500ms

### Quality Requirements

- \[ \] No user-facing changes (UI identical)
- \[ \] No breaking changes to existing functionality
- \[ \] All existing tests still pass
- \[ \] New integration tests pass
- \[ \] Error handling is graceful
- \[ \] Logging is informative
- \[ \] Code reviewed and approved

______________________________________________________________________

## Post-Deployment Monitoring

After deploying Stage 2 to production/users:

### Metrics to Track

1. **Startup time** - Is it acceptable for users?
2. **Error rate** - Any database-related crashes?
3. **Rescan frequency** - How often do users click "Rescan"?
4. **Database size** - Growing as expected?
5. **User feedback** - Any complaints about performance?

### Log Analysis

Monitor logs for:

- `Database integrity issues` - Indicates corruption
- `Scan completed in X.XXs` - Track performance trends
- `Failed to generate hash` - Permission issues
- `Restore failed` - Backup/restore problems

### Rollback Triggers

Consider rolling back if:

- Startup time > 60s for typical libraries
- Database corruption reported by > 1% of users
- Critical functionality broken (can't browse/search/queue)
- Memory usage > 500 MB
- User complaints about performance

______________________________________________________________________

## Next Steps

After Stage 2 completion:

1. ✅ All validation tests pass
2. ✅ Performance benchmarks met
3. ✅ User acceptance testing complete
4. ✅ Documentation updated
5. 📝 Proceed to Stage 3 (Admin UI)

In Stage 3, we'll expose database features in the admin UI:

- Synchronize Library button (explicit control over rescans)
- Download Database Backup button
- Restore from Backup upload form

______________________________________________________________________

**Document Status:** Ready for Implementation (After Stage 1)
**Last Updated:** 2026-01-09
**Approved By:** Pending
