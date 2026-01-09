# PiKaraoke Database Upgrade - Implementation Order

**Created:** 2026-01-09
**Status:**  Planning Complete - Implementation Guide
**Purpose:** Step-by-step implementation sequence with dependencies

______________________________________________________________________

## Overview

This document provides the exact order in which to implement the database upgrade, ensuring dependencies are respected and changes can be validated incrementally.

**Key Principle:** Each step builds on previous steps. Never skip ahead or implement out of order.

______________________________________________________________________

## Pre-Implementation Checklist

Before starting Stage 1:

- \[ \] All planning documents reviewed and approved
- \[ \] Development environment set up
- \[ \] Git branch created: `feature/sqlite-database-upgrade`
- \[ \] Backup of current codebase taken
- \[ \] Test environment available (separate from production)

______________________________________________________________________

## Stage 1: Core Database Layer

**Goal:** Create and validate the database module in complete isolation

**Estimated Time:** 1-2 days

### Step 1.1: Create Database Module File

**File to Create:** `pikaraoke/lib/karaoke_database.py`

**Dependencies:** None (standalone module)

**Order of Implementation:**

1. **Class skeleton and imports** (lines 1-30)

   ```python
   import sqlite3
   import os
   import hashlib
   from pathlib import Path
   from typing import Dict, List, Optional, Tuple
   import logging
   from datetime import datetime
   ```

2. **`__init__()` method** (database initialization)

   - Connection setup
   - WAL mode configuration
   - Schema creation call

3. **`_create_schema()` private method**

   - Create `songs` table (WITHOUT Stage 4 fields initially)
   - Create indexes
   - Create `metadata` table
   - Initial schema only:
     ```sql
     CREATE TABLE IF NOT EXISTS songs (
         id INTEGER PRIMARY KEY AUTOINCREMENT,
         file_path TEXT UNIQUE NOT NULL,
         file_hash TEXT,
         filename TEXT NOT NULL,
         artist TEXT,
         title TEXT,
         variant TEXT,
         format TEXT NOT NULL,
         search_blob TEXT,
         is_visible INTEGER DEFAULT 1,
         created_at TEXT DEFAULT CURRENT_TIMESTAMP,
         updated_at TEXT DEFAULT CURRENT_TIMESTAMP
     );
     ```

4. **`_generate_file_hash()` private method**

   - SHA256 hash generation
   - First 16KB + file size approach

5. **`_detect_format()` private method**

   - Extension-based detection
   - CDG/ASS pairing logic
   - Must be implemented before `scan_library()`

6. **Basic CRUD methods** (in this order):

   - `get_song_by_path(path)` - Read single song
   - `get_all_songs()` - Read all songs
   - `get_all_song_paths()` - Critical for Stage 2 integration
   - `get_song_count()` - Simple query
   - `_insert_song()` - Private helper for scan

7. **`scan_library()` method** (most complex)

   - Phase 1: Scan filesystem
   - Phase 2: Update existing (by hash)
   - Phase 3: Insert new
   - Phase 4: Delete missing
   - **CRITICAL:** Implement complete deletion logic (fix reference bug)

8. **Backup/restore methods**:

   - `backup_database(backup_dir)` - File copy approach
   - `restore_database(backup_path)` - Replace current DB
   - `get_backup_list()` - List available backups

9. **Utility methods**:

   - `get_metadata(key)` - Read metadata table
   - `set_metadata(key, value)` - Write metadata table
   - `close()` - Cleanup

**Validation Checkpoint:**

- \[ \] Module imports without errors
- \[ \] Can instantiate `KaraokeDatabase()` class
- \[ \] Database file created at correct location
- \[ \] Schema matches Stage 1 design (verified with SQLite viewer)

______________________________________________________________________

### Step 1.2: Create Unit Tests

**File to Create:** `tests/test_karaoke_database.py`

**Dependencies:** Step 1.1 complete

**Test Implementation Order:**

1. **Setup/teardown fixtures**

   ```python
   @pytest.fixture
   def temp_db():
       db = KaraokeDatabase(db_path=":memory:")
       yield db
       db.close()
   ```

2. **Basic tests** (verify module works):

   - `test_database_initialization()` - DB file created
   - `test_schema_creation()` - Tables exist
   - `test_get_song_count_empty()` - Returns 0 initially

3. **Hash generation tests**:

   - `test_generate_file_hash()` - Consistent hash
   - `test_hash_detects_content_change()` - Different content = different hash

4. **Format detection tests**:

   - `test_detect_format_mp3()` - Detects MP3
   - `test_detect_format_cdg_pair()` - Detects CDG when MP3+CDG present
   - `test_detect_format_mp4()` - Detects MP4
   - `test_detect_format_ass_pair()` - Detects ASS when MP4+ASS present

5. **CRUD tests**:

   - `test_insert_and_get_song()` - Insert and retrieve
   - `test_get_all_songs()` - Multiple songs
   - `test_get_song_by_path()` - Find by path

6. **Scan library tests** (most critical):

   - `test_scan_library_adds_new_songs()` - Initial scan
   - `test_scan_library_detects_moves()` - Move file, rescan (hash match)
   - `test_scan_library_detects_deletes()` - Delete file, rescan
   - `test_scan_library_handles_cdg_pairs()` - Only stores .mp3, not .cdg
   - `test_scan_library_stats()` - Returns correct counts

7. **Backup/restore tests**:

   - `test_backup_database()` - Creates backup file
   - `test_restore_database()` - Restores from backup
   - `test_backup_list()` - Lists backups correctly

8. **Edge case tests**:

   - `test_unicode_filenames()` - UTF-8 handling
   - `test_special_characters_in_path()` - Spaces, symbols
   - `test_concurrent_reads()` - WAL mode allows concurrent access

**Validation Checkpoint:**

- \[ \] All unit tests pass (100% pass rate)
- \[ \] Code coverage > 80% for karaoke_database.py
- \[ \] No flaky tests (run 3 times, all pass)
- \[ \] Performance: 1000 song scan completes in \< 15 seconds

______________________________________________________________________

### Step 1.3: Manual Testing (Test Library)

**Dependencies:** Steps 1.1 and 1.2 complete

**Manual Test Procedure:**

1. Create test library with known files:

   ```
   test_library/
    Artist1 - Song1.mp3
    Artist1 - Song1.cdg
    Artist2 - Song2.mp4
    Artist3 - Song3.mp3
    subfolder/
        Artist4 - Song4.mp3
   ```

2. Run interactive Python session:

   ```python
   from pikaraoke.lib.karaoke_database import KaraokeDatabase

   db = KaraokeDatabase()
   stats = db.scan_library("test_library")
   print(f"Added: {stats['added']}")  # Should be 4

   songs = db.get_all_songs()
   for song in songs:
       print(f"{song['format']}: {song['filename']}")

   # Test move detection
   # (manually move Artist1 - Song1.mp3 to subfolder/)
   stats = db.scan_library("test_library")
   print(f"Moved: {stats['moved']}")  # Should be 1

   # Test delete detection
   # (manually delete Artist3 - Song3.mp3)
   stats = db.scan_library("test_library")
   print(f"Deleted: {stats['deleted']}")  # Should be 1

   # Test backup
   db.backup_database()
   backups = db.get_backup_list()
   print(f"Backups: {backups}")
   ```

**Validation Checkpoint:**

- \[ \] Initial scan detects all 4 songs
- \[ \] CDG pair stored as single "CDG" format entry (not two separate files)
- \[ \] Moving file detected correctly (moved count increments)
- \[ \] Deleting file detected correctly (deleted count increments)
- \[ \] Backup file created successfully
- \[ \] Database file size reasonable (\< 50KB for 4 songs)

______________________________________________________________________

### Stage 1 Completion Criteria

**Before proceeding to Stage 2:**

- \[ \]  `karaoke_database.py` created and imports successfully
- \[ \]  All unit tests pass (no failures, no skips)
- \[ \]  Manual testing shows correct behavior
- \[ \]  Code review completed (if working in team)
- \[ \]  Performance benchmarks met (\< 15s for 1K songs)
- \[ \]  No memory leaks (test with 10K+ songs)
- \[ \]  Documentation comments added to public methods
- \[ \]  Git commit created: `feat(database): implement KaraokeDatabase core module`

**Deliverables:**

1. `pikaraoke/lib/karaoke_database.py` (~400-500 lines)
2. `tests/test_karaoke_database.py` (~300-400 lines)
3. Test library directory with sample files
4. Performance benchmark results documented

______________________________________________________________________

## Stage 2: Read-Only Integration

**Goal:** Integrate database into main app with ZERO breaking changes

**Estimated Time:** 0.5-1 day

**Critical Principle:** Both systems (DB + SongList) run in parallel. Users notice NO difference.

______________________________________________________________________

### Step 2.1: Modify Karaoke Class Initialization

**File to Modify:** `pikaraoke/karaoke.py`

**Dependencies:** Stage 1 complete

**Changes (in order):**

1. **Add import** (top of file, ~line 20):

   ```python
   from pikaraoke.lib.karaoke_database import KaraokeDatabase
   ```

2. **Modify `__init__()` method** (~line 299):

   **Before:**

   ```python
   self.available_songs = SongList()
   self.get_available_songs()
   ```

   **After:**

   ```python
   # Initialize database (new)
   self.db = KaraokeDatabase()

   # Initialize song list (legacy - keep for now)
   self.available_songs = SongList()

   # Scan library with database
   logging.info("Scanning library with database...")
   scan_stats = self.db.scan_library(self.download_path)
   logging.info(
       f"Database scan: {scan_stats['added']} added, "
       f"{scan_stats['moved']} moved, {scan_stats['deleted']} deleted"
   )

   # Populate legacy song list from database
   all_paths = self.db.get_all_song_paths()
   self.available_songs.update(all_paths)

   logging.info(
       f"Song list populated with {len(self.available_songs)} songs from database"
   )
   ```

**Validation Checkpoint:**

- \[ \] App starts without errors
- \[ \] Database file created at `{get_data_directory()}/pikaraoke.db`
- \[ \] Logs show scan statistics
- \[ \] Song list populated correctly

______________________________________________________________________

### Step 2.2: Integration Testing

**Dependencies:** Step 2.1 complete

**Test Cases (in order):**

1. **Startup test**:

   - Start app with existing library
   - Verify both database and song list initialized
   - Check logs for scan statistics
   - Verify no error messages

2. **Browse functionality**:

   - Open `/browse` page
   - Verify all songs visible
   - Verify search works
   - Verify sorting works
   - **Expected:** Identical to pre-integration behavior

3. **Queue functionality**:

   - Add song to queue
   - Play song
   - Skip song
   - **Expected:** Identical to pre-integration behavior

4. **Search functionality**:

   - Search by artist
   - Search by title
   - Search partial match
   - **Expected:** Identical to pre-integration behavior

5. **Persistence test**:

   - Restart app (close and reopen)
   - Verify database file persists
   - Verify scan detects no changes (0 added/moved/deleted)
   - Verify song list repopulated correctly

6. **Move detection test**:

   - Move a file in library (outside app)
   - Restart app
   - Verify scan detects move (moved count = 1)
   - Verify song still appears in browse

7. **Delete detection test**:

   - Delete a file in library (outside app)
   - Restart app
   - Verify scan detects deletion (deleted count = 1)
   - Verify song removed from browse

**Validation Checkpoint:**

- \[ \] All 7 test cases pass
- \[ \] No functional regressions detected
- \[ \] Performance acceptable (startup \< previous + 5s on first run)
- \[ \] Subsequent startups fast (\< 2s for database init)

______________________________________________________________________

### Step 2.3: Performance Benchmarking

**Dependencies:** Step 2.2 complete

**Benchmarks to Run:**

| Metric | Target | Measured | Pass/Fail |
|--------|--------|----------|-----------|
| First startup (1K songs) | \< 20s | \_\_\_ | \_\_\_ |
| Subsequent startup | \< 2s | \_\_\_ | \_\_\_ |
| Browse page load | \< 1s | \_\_\_ | \_\_\_ |
| Search response | \< 500ms | \_\_\_ | \_\_\_ |
| Memory usage increase | \< 10MB | \_\_\_ | \_\_\_ |

**If any benchmark fails:** Optimize before proceeding to Stage 3.

______________________________________________________________________

### Stage 2 Completion Criteria

**Before proceeding to Stage 3:**

- \[ \]  Database integrated into `karaoke.py`
- \[ \]  All integration tests pass
- \[ \]  All performance benchmarks met
- \[ \]  Zero breaking changes confirmed
- \[ \]  User acceptance testing complete (manual test by end user)
- \[ \]  Logs reviewed (no unexpected warnings/errors)
- \[ \]  Git commit created: `feat(database): integrate KaraokeDatabase into main app`

**Deliverables:**

1. Modified `pikaraoke/karaoke.py` (~10 lines changed)
2. Integration test results documented
3. Performance benchmark results documented

______________________________________________________________________

## Stage 3: Admin UI - Library Management

**Goal:** Expose database features through web interface

**Estimated Time:** 1-2 days

______________________________________________________________________

### Step 3.1: Create Flask Routes

**File to Modify:** `pikaraoke/routes.py` (or create new blueprint)

**Dependencies:** Stage 2 complete

**Implementation Order:**

1. **Add imports** (top of file):

   ```python
   from flask import jsonify, request, send_file
   from werkzeug.utils import secure_filename
   import tempfile
   import os
   ```

2. **Route 1: Library Statistics** (simplest, implement first):

   ```python
   @app.route("/admin/library_stats")
   @requires_admin
   def library_stats():
       total = k.db.get_song_count()
       last_scan = k.db.get_metadata("last_scan")
       return jsonify(
           {"total_songs": total, "last_scan": last_scan, "database_path": k.db.db_path}
       )
   ```

3. **Route 2: Synchronize Library** (core functionality):

   ```python
   @app.route("/admin/sync_library")
   @requires_admin
   def sync_library():
       stats = k.db.scan_library(k.download_path)
       k.available_songs.clear()
       k.available_songs.update(k.db.get_all_song_paths())
       return jsonify(
           {
               "success": True,
               "message": f"Library synchronized. {stats['added']} added, "
               f"{stats['moved']} moved, {stats['deleted']} deleted",
               "stats": stats,
               "total_songs": k.db.get_song_count(),
           }
       )
   ```

4. **Route 3: Download Backup** (file serving):

   ```python
   @app.route("/admin/download_backup")
   @requires_admin
   def download_backup():
       backup_path = k.db.backup_database()
       return send_file(
           backup_path,
           as_attachment=True,
           download_name=f"pikaraoke_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db",
       )
   ```

5. **Route 4: Restore Backup** (file upload, most complex):

   ```python
   @app.route("/admin/restore_backup", methods=["POST"])
   @requires_admin
   def restore_backup():
       if "backup_file" not in request.files:
           return jsonify({"success": False, "message": "No file uploaded"}), 400

       file = request.files["backup_file"]
       if file.filename == "":
           return jsonify({"success": False, "message": "No file selected"}), 400

       # Security: validate file extension
       if not file.filename.endswith(".db"):
           return jsonify({"success": False, "message": "Invalid file type"}), 400

       # Save to temp file
       temp_path = os.path.join(tempfile.gettempdir(), secure_filename(file.filename))
       file.save(temp_path)

       # Restore database
       k.db.restore_database(temp_path)

       # Repopulate song list
       k.available_songs.clear()
       k.available_songs.update(k.db.get_all_song_paths())

       # Clean up temp file
       os.remove(temp_path)

       return jsonify(
           {
               "success": True,
               "message": f"Database restored. {k.db.get_song_count()} songs loaded.",
               "total_songs": k.db.get_song_count(),
           }
       )
   ```

**Validation Checkpoint:**

- \[ \] All 4 routes added without syntax errors
- \[ \] App starts successfully
- \[ \] Can access routes via curl/Postman (before UI implementation)

______________________________________________________________________

### Step 3.2: Update Admin UI Template

**File to Modify:** `pikaraoke/templates/info.html`

**Dependencies:** Step 3.1 complete

**Changes (in order):**

1. **Find existing "Refresh" section** (~line 410)

2. **Replace with new "Manage Song Library" section**:

   ```html
   <!-- Replace old "Refresh" section with new "Manage Song Library" -->
   <div class="box">
       <h3 class="title is-4"> Manage Song Library</h3>

       <!-- Library Status -->
       <div id="library-status" class="content">
           <p><strong>Total Songs:</strong> <span id="total-songs">Loading...</span></p>
           <p><strong>Last Scan:</strong> <span id="last-scan">Loading...</span></p>
       </div>

       <!-- Synchronize Button -->
       <div class="field">
           <button id="sync-library-btn" class="button is-primary">
               <span class="icon"><i class="fa fa-sync"></i></span>
               <span>Synchronize Library</span>
           </button>
           <p class="help">Scan library for new, moved, or deleted songs</p>
       </div>

       <!-- Backup/Restore -->
       <div class="field">
           <button id="download-backup-btn" class="button is-info">
               <span class="icon"><i class="fa fa-download"></i></span>
               <span>Download Backup</span>
           </button>
           <p class="help">Export database for safekeeping</p>
       </div>

       <div class="field">
           <div class="file has-name">
               <label class="file-label">
                   <input id="restore-backup-input" class="file-input" type="file" accept=".db">
                   <span class="file-cta">
                       <span class="file-icon"><i class="fa fa-upload"></i></span>
                       <span class="file-label">Restore Backup</span>
                   </span>
                   <span id="restore-filename" class="file-name">No file selected</span>
               </label>
           </div>
           <p class="help">Upload a backup file to restore</p>
       </div>

       <!-- Status Messages -->
       <div id="library-message" class="notification is-hidden"></div>
   </div>
   ```

**Validation Checkpoint:**

- \[ \] Template renders without errors
- \[ \] Section appears on `/info` page
- \[ \] Buttons visible and styled correctly
- \[ \] Layout responsive on mobile

______________________________________________________________________

### Step 3.3: Add JavaScript Handlers

**File to Modify:** `pikaraoke/templates/info.html` (add at bottom of file)

**Dependencies:** Step 3.2 complete

**Implementation Order:**

1. **Load statistics on page load** (simplest):

   ```javascript
   <script>
   $(document).ready(function() {
       loadLibraryStats();
   });

   function loadLibraryStats() {
       $.getJSON('/admin/library_stats', function(data) {
           $('#total-songs').text(data.total_songs);
           $('#last-scan').text(data.last_scan || 'Never');
       }).fail(function() {
           $('#total-songs').text('Error');
           $('#last-scan').text('Error');
       });
   }
   ```

2. **Synchronize library handler**:

   ```javascript
   $('#sync-library-btn').click(function() {
       const btn = $(this);
       btn.addClass('is-loading');

       $.getJSON('/admin/sync_library', function(data) {
           showMessage('success', data.message);
           $('#total-songs').text(data.total_songs);
           $('#last-scan').text('Just now');
       }).fail(function() {
           showMessage('danger', 'Synchronization failed');
       }).always(function() {
           btn.removeClass('is-loading');
       });
   });
   ```

3. **Download backup handler** (simple redirect):

   ```javascript
   $('#download-backup-btn').click(function() {
       window.location.href = '/admin/download_backup';
       showMessage('info', 'Downloading backup...');
   });
   ```

4. **Restore backup handler** (file upload, most complex):

   ```javascript
   $('#restore-backup-input').change(function() {
       const filename = $(this).val().split('\\').pop();
       $('#restore-filename').text(filename);

       if (filename) {
           const formData = new FormData();
           formData.append('backup_file', this.files[0]);

           if (confirm('Restore will replace current database. Continue?')) {
               $.ajax({
                   url: '/admin/restore_backup',
                   type: 'POST',
                   data: formData,
                   processData: false,
                   contentType: false,
                   success: function(data) {
                       showMessage('success', data.message);
                       loadLibraryStats();
                   },
                   error: function() {
                       showMessage('danger', 'Restore failed');
                   }
               });
           }
       }
   });

   function showMessage(type, message) {
       const msg = $('#library-message');
       msg.removeClass('is-hidden is-success is-danger is-info');
       msg.addClass('is-' + type);
       msg.text(message);
       setTimeout(function() { msg.addClass('is-hidden'); }, 5000);
   }
   </script>
   ```

**Validation Checkpoint:**

- \[ \] JavaScript loads without errors (check browser console)
- \[ \] Statistics load on page load
- \[ \] Synchronize button works (shows loading state, updates stats)
- \[ \] Download button triggers file download
- \[ \] Restore button uploads file and updates database

______________________________________________________________________

### Step 3.4: Integration Testing

**Dependencies:** Steps 3.1-3.3 complete

**Test Cases (in order):**

1. **Load info page**:

   - Navigate to `/info`
   - Verify "Manage Song Library" section appears
   - Verify statistics load correctly
   - Check browser console for errors (should be none)

2. **Synchronize library**:

   - Click "Synchronize Library" button
   - Verify loading state appears
   - Verify success message appears
   - Verify statistics update

3. **Download backup**:

   - Click "Download Backup" button
   - Verify file downloads
   - Verify filename format: `pikaraoke_backup_YYYYMMDD_HHMMSS.db`
   - Verify file size > 0

4. **Restore backup**:

   - Upload previously downloaded backup
   - Verify confirmation prompt appears
   - Click "OK"
   - Verify success message
   - Verify statistics update

5. **Error handling**:

   - Try uploading non-.db file (should show error)
   - Try restoring while app is playing song (should handle gracefully)

6. **Mobile responsiveness**:

   - Open on mobile device/emulator
   - Verify layout adapts correctly
   - Verify buttons are tap-friendly

**Validation Checkpoint:**

- \[ \] All 6 test cases pass
- \[ \] No JavaScript errors in console
- \[ \] No Flask errors in server logs
- \[ \] Mobile experience acceptable

______________________________________________________________________

### Stage 3 Completion Criteria

**Before proceeding to Stage 4:**

- \[ \]  All 4 Flask routes implemented and tested
- \[ \]  Admin UI updated and functional
- \[ \]  JavaScript handlers working correctly
- \[ \]  All integration tests pass
- \[ \]  Security review complete (admin auth, file validation)
- \[ \]  Mobile responsiveness verified
- \[ \]  User acceptance testing complete
- \[ \]  Git commit created: `feat(admin): add library management UI`

**Deliverables:**

1. Modified `pikaraoke/routes.py` (~100 lines added)
2. Modified `pikaraoke/templates/info.html` (~150 lines added/modified)
3. Integration test results documented
4. Screenshots of working UI

______________________________________________________________________

## Stage 4: Metadata Enrichment (Optional)

**Goal:** Add background metadata enrichment with confidence scoring

**Estimated Time:** 2-3 days

**Note:** This stage is OPTIONAL but recommended for enhanced user experience.

______________________________________________________________________

### Step 4.1: Update Database Schema

**File to Modify:** `pikaraoke/lib/karaoke_database.py`

**Dependencies:** Stage 3 complete

**Schema Changes (in `_create_schema()`):**

1. **Update `songs` table** (add new fields):

   ```sql
   ALTER TABLE songs ADD COLUMN year INTEGER;
   ALTER TABLE songs ADD COLUMN genre TEXT;
   ALTER TABLE songs ADD COLUMN youtube_id TEXT;
   ALTER TABLE songs ADD COLUMN confidence REAL DEFAULT 0.0;
   ALTER TABLE songs ADD COLUMN metadata_status TEXT DEFAULT 'pending';
   ALTER TABLE songs ADD COLUMN enrichment_attempts INTEGER DEFAULT 0;
   ALTER TABLE songs ADD COLUMN last_enrichment_attempt TEXT;
   ```

2. **Create `enrichment_queue` table**:

   ```sql
   CREATE TABLE IF NOT EXISTS enrichment_queue (
       id INTEGER PRIMARY KEY AUTOINCREMENT,
       song_id INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
       priority INTEGER DEFAULT 0,
       queued_at TEXT DEFAULT CURRENT_TIMESTAMP,
       UNIQUE(song_id)
   );
   CREATE INDEX idx_enrichment_priority ON enrichment_queue(priority DESC, queued_at);
   ```

3. **Create `enrichment_state` table**:

   ```sql
   CREATE TABLE IF NOT EXISTS enrichment_state (
       key TEXT PRIMARY KEY,
       value TEXT
   );
   ```

**Migration Strategy:**

Since we're adding columns to existing table, implement migration logic:

```python
def _migrate_schema(self):
    """Migrate existing database to latest schema."""
    cursor = self.conn.cursor()

    # Check if new columns exist
    cursor.execute("PRAGMA table_info(songs)")
    columns = [row[1] for row in cursor.fetchall()]

    # Add missing columns
    if "confidence" not in columns:
        cursor.execute("ALTER TABLE songs ADD COLUMN confidence REAL DEFAULT 0.0")
    if "metadata_status" not in columns:
        cursor.execute(
            "ALTER TABLE songs ADD COLUMN metadata_status TEXT DEFAULT 'pending'"
        )
    # ... repeat for all new columns

    self.conn.commit()
```

**Validation Checkpoint:**

- \[ \] Existing databases migrate without errors
- \[ \] New columns added successfully
- \[ \] New tables created
- \[ \] Indexes created

______________________________________________________________________

### Step 4.2: Implement Filename Parsing (Phase 4A)

**File to Modify:** `pikaraoke/lib/karaoke_database.py`

**Dependencies:** Step 4.1 complete

**Implementation Order:**

1. **Add `_parse_filename()` private method**:

   ```python
   def _parse_filename(self, filename: str) -> Dict[str, any]:
       """Parse metadata from filename using pattern matching."""
       # Remove extension
       name = os.path.splitext(filename)[0]

       # Pattern 1: "Artist - Title"
       if " - " in name:
           parts = name.split(" - ", 1)
           return {
               "artist": parts[0].strip(),
               "title": parts[1].strip(),
               "confidence": 0.60,
           }

       # Pattern 2: "Title (Artist)"
       # Pattern 3: YouTube ID detection
       # ... (see stage4-metadata-enrichment.md for full patterns)

       # Fallback: filename is title
       return {"artist": None, "title": name, "confidence": 0.20}
   ```

2. **Update `_insert_song()` to use parsing**:

   ```python
   def _insert_song(self, path, file_hash, format):
       filename = os.path.basename(path)
       metadata = self._parse_filename(filename)

       self.conn.execute(
           """
           INSERT INTO songs (file_path, file_hash, filename, format,
                             artist, title, confidence, metadata_status)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'parsed')
       """,
           (
               path,
               file_hash,
               filename,
               format,
               metadata["artist"],
               metadata["title"],
               metadata["confidence"],
           ),
       )
   ```

3. **Add to enrichment queue**:

   ```python
   def _queue_for_enrichment(self, song_id: int, priority: int = 0):
       """Add song to enrichment queue."""
       try:
           self.conn.execute(
               """
               INSERT OR IGNORE INTO enrichment_queue (song_id, priority)
               VALUES (?, ?)
           """,
               (song_id, priority),
           )
           self.conn.commit()
       except sqlite3.IntegrityError:
           pass  # Already queued
   ```

**Validation Checkpoint:**

- \[ \] Filename parsing extracts artist/title correctly
- \[ \] Confidence scores assigned reasonably
- \[ \] Songs added to enrichment queue
- \[ \] Unit tests updated and passing

______________________________________________________________________

### Step 4.3: Implement Enrichment Worker (Phase 4B)

**File to Create:** `pikaraoke/lib/enrichment_worker.py`

**Dependencies:** Step 4.2 complete

**Implementation Order:**

1. **Class skeleton and imports**:

   ```python
   from threading import Thread, Event
   import time
   import logging
   from typing import Dict, Optional
   import requests
   ```

2. **`__init__()` method**:

   ```python
   class EnrichmentWorker(Thread):
       def __init__(self, db: "KaraokeDatabase", api_key: str, rate_limit: float = 5.0):
           super().__init__(daemon=True, name="EnrichmentWorker")
           self.db = db
           self.api_key = api_key
           self.rate_limit = rate_limit
           self.min_interval = 1.0 / rate_limit
           self._stop_event = Event()
           self._pause_event = Event()
           self._pause_event.set()  # Start unpaused
   ```

3. **`run()` method** (main loop):

   ```python
   def run(self):
       """Main worker loop."""
       self.db.set_metadata("worker_started_at", datetime.now().isoformat())

       while not self._stop_event.is_set():
           self._pause_event.wait()  # Block if paused

           song = self._get_next_song()
           if not song:
               time.sleep(1.0)
               continue

           success = self._enrich_song(song)
           self._update_progress(success)

           time.sleep(self.min_interval)  # Rate limiting
   ```

4. **`_get_next_song()` helper**:

   ```python
   def _get_next_song(self) -> Optional[Dict]:
       """Get next song from enrichment queue."""
       cursor = self.db.conn.cursor()
       cursor.execute(
           """
           SELECT eq.id, s.*
           FROM enrichment_queue eq
           JOIN songs s ON eq.song_id = s.id
           ORDER BY eq.priority DESC, eq.queued_at ASC
           LIMIT 1
       """
       )
       row = cursor.fetchone()
       return dict(row) if row else None
   ```

5. **`_enrich_song()` method** (Last.FM API call):

   ```python
   def _enrich_song(self, song: Dict) -> bool:
       """Enrich a single song with external API data."""
       try:
           # Call Last.FM API
           response = requests.get(
               "https://ws.audioscrobbler.com/2.0/",
               params={
                   "method": "track.getInfo",
                   "artist": song["artist"],
                   "track": song["title"],
                   "api_key": self.api_key,
                   "format": "json",
               },
               timeout=5,
           )

           if response.status_code == 200:
               data = response.json()
               # Extract year, genre, canonical names
               # Calculate confidence score
               # Update database
               return True
           else:
               return False
       except Exception as e:
           logging.error(f"Enrichment failed for {song['filename']}: {e}")
           return False
   ```

6. **Control methods**:

   ```python
   def pause(self):
       self._pause_event.clear()


   def resume(self):
       self._pause_event.set()


   def stop(self):
       self._stop_event.set()


   def get_progress(self) -> Dict:
       total = int(self.db.get_metadata("total_processed") or 0)
       enriched = int(self.db.get_metadata("total_enriched") or 0)
       failed = int(self.db.get_metadata("total_failed") or 0)
       return {"total": total, "enriched": enriched, "failed": failed}
   ```

**Validation Checkpoint:**

- \[ \] Worker thread starts successfully
- \[ \] Processes queue in priority order
- \[ \] Respects rate limit (measure with timer)
- \[ \] Can pause/resume/stop gracefully
- \[ \] Progress persists to database

______________________________________________________________________

### Step 4.4: Integrate Worker into Database

**File to Modify:** `pikaraoke/lib/karaoke_database.py`

**Dependencies:** Step 4.3 complete

**Add methods:**

```python
def start_enrichment(self, api_key: str):
    """Start background enrichment worker."""
    from pikaraoke.lib.enrichment_worker import EnrichmentWorker

    if hasattr(self, "enrichment_worker") and self.enrichment_worker.is_alive():
        logging.warning("Enrichment worker already running")
        return

    self.enrichment_worker = EnrichmentWorker(self, api_key)
    self.enrichment_worker.start()
    logging.info("Enrichment worker started")


def stop_enrichment(self):
    """Stop background enrichment worker."""
    if hasattr(self, "enrichment_worker"):
        self.enrichment_worker.stop()
        self.enrichment_worker.join(timeout=5.0)


def pause_enrichment(self):
    if hasattr(self, "enrichment_worker"):
        self.enrichment_worker.pause()


def resume_enrichment(self):
    if hasattr(self, "enrichment_worker"):
        self.enrichment_worker.resume()


def get_enrichment_progress(self) -> Dict:
    if hasattr(self, "enrichment_worker"):
        return self.enrichment_worker.get_progress()
    return {"total": 0, "enriched": 0, "failed": 0}
```

**Validation Checkpoint:**

- \[ \] Can start worker from database instance
- \[ \] Worker processes queue automatically
- \[ \] Can retrieve progress stats
- \[ \] Can pause/resume/stop worker

______________________________________________________________________

### Step 4.5: Add Admin UI for Enrichment

**File to Modify:** `pikaraoke/templates/info.html`

**Dependencies:** Step 4.4 complete

**Add new section after "Manage Song Library":**

```html
<div class="box">
    <h3 class="title is-4"> Metadata Enrichment</h3>

    <div id="enrichment-status" class="content">
        <p><strong>Status:</strong> <span id="worker-status">Stopped</span></p>
        <progress id="enrichment-progress" class="progress is-primary" value="0" max="100">0%</progress>
        <p><strong>Progress:</strong> <span id="enrichment-stats">0/0 processed</span></p>
    </div>

    <div class="field">
        <button id="start-enrichment-btn" class="button is-success">
            <span class="icon"><i class="fa fa-play"></i></span>
            <span>Start Enrichment</span>
        </button>
        <button id="pause-enrichment-btn" class="button is-warning" disabled>
            <span class="icon"><i class="fa fa-pause"></i></span>
            <span>Pause</span>
        </button>
        <button id="stop-enrichment-btn" class="button is-danger" disabled>
            <span class="icon"><i class="fa fa-stop"></i></span>
            <span>Stop</span>
        </button>
    </div>
</div>
```

**Add Flask routes:**

```python
@app.route("/admin/start_enrichment")
@requires_admin
def start_enrichment():
    api_key = os.environ.get("LASTFM_API_KEY")
    if not api_key:
        return jsonify({"success": False, "message": "API key not configured"}), 400
    k.db.start_enrichment(api_key)
    return jsonify({"success": True, "message": "Enrichment started"})


@app.route("/admin/enrichment_progress")
@requires_admin
def enrichment_progress():
    progress = k.db.get_enrichment_progress()
    return jsonify(progress)
```

**Add JavaScript polling:**

```javascript
let progressInterval = null;

$('#start-enrichment-btn').click(function() {
    $.getJSON('/admin/start_enrichment', function(data) {
        showMessage('success', data.message);
        startProgressPolling();
    });
});

function startProgressPolling() {
    if (progressInterval) return;

    progressInterval = setInterval(function() {
        $.getJSON('/admin/enrichment_progress', function(data) {
            const percent = data.total > 0 ? (data.enriched / data.total * 100) : 0;
            $('#enrichment-progress').val(percent);
            $('#enrichment-stats').text(`${data.enriched}/${data.total} processed`);

            if (data.enriched >= data.total) {
                clearInterval(progressInterval);
                progressInterval = null;
            }
        });
    }, 2000);  // Poll every 2 seconds
}
```

**Validation Checkpoint:**

- \[ \] Enrichment section appears on info page
- \[ \] Start button launches worker
- \[ \] Progress bar updates in real-time
- \[ \] Pause/stop buttons work correctly

______________________________________________________________________

### Stage 4 Completion Criteria

**Before considering project complete:**

- \[ \]  Schema updated with enrichment fields
- \[ \]  Filename parsing implemented and tested
- \[ \]  Enrichment worker implemented and tested
- \[ \]  Admin UI shows enrichment progress
- \[ \]  API key configuration documented
- \[ \]  All unit tests updated and passing
- \[ \]  Performance acceptable (doesn't slow down app)
- \[ \]  User documentation updated
- \[ \]  Git commit created: `feat(metadata): add background enrichment with confidence scoring`

**Deliverables:**

1. Modified `pikaraoke/lib/karaoke_database.py` (~100 lines added)
2. New `pikaraoke/lib/enrichment_worker.py` (~200 lines)
3. Modified `pikaraoke/templates/info.html` (~100 lines added)
4. Updated `pikaraoke/routes.py` (~50 lines added)
5. Updated tests for all new functionality
6. User documentation for API key setup

______________________________________________________________________

## Post-Implementation Checklist

**After all stages complete:**

- \[ \] Full regression testing on test library
- \[ \] Performance benchmarks all met
- \[ \] User acceptance testing complete
- \[ \] Documentation updated (README, user guide)
- \[ \] Code review completed
- \[ \] All commits merged to main branch
- \[ \] Tag release version (e.g., `v2.0.0-database-upgrade`)
- \[ \] Deployment plan documented
- \[ \] Rollback plan tested
- \[ \] Monitoring in place (logs, metrics)

______________________________________________________________________

## Critical Dependencies Summary

```
Stage 1 (Core Database)

     Step 1.1: Create karaoke_database.py
     Step 1.2: Create unit tests
     Step 1.3: Manual testing

     (All Stage 1 tests must pass)

Stage 2 (Integration)

     Step 2.1: Modify karaoke.py
     Step 2.2: Integration testing
     Step 2.3: Performance benchmarking

     (Zero breaking changes verified)

Stage 3 (Admin UI)

     Step 3.1: Create Flask routes
     Step 3.2: Update template
     Step 3.3: Add JavaScript
     Step 3.4: Integration testing

     (Optional - can skip to deployment)

Stage 4 (Metadata) - OPTIONAL

     Step 4.1: Update schema
     Step 4.2: Filename parsing
     Step 4.3: Enrichment worker
     Step 4.4: Integrate worker
     Step 4.5: Admin UI
```

______________________________________________________________________

## Estimated Timeline

| Stage | Estimated Time | Can Skip? |
|-------|----------------|-----------|
| Stage 1 | 1-2 days |  No |
| Stage 2 | 0.5-1 day |  No |
| Stage 3 | 1-2 days |  No |
| Stage 4 | 2-3 days |  Yes |
| **Total** | **4.5-8 days** | |

**Note:** Times assume single developer working full-time. Adjust for part-time work or team collaboration.

______________________________________________________________________

## Common Pitfalls to Avoid

1. **Don't skip unit tests** - They catch bugs early and save time later
2. **Don't implement out of order** - Dependencies exist for a reason
3. **Don't rush validation checkpoints** - Thorough testing prevents rework
4. **Don't skip Stage 2 performance testing** - Database must not slow down app
5. **Don't forget migration logic** - Existing users need smooth upgrade path
6. **Don't hardcode paths** - Use `get_data_directory()` for cross-platform support
7. **Don't expose technical errors to users** - Show friendly messages in UI
8. **Don't forget to close database connections** - Prevents corruption on crashes

______________________________________________________________________

## Success Indicators

**You're on track if:**

- Each stage completion criteria checklist is 100% complete before proceeding
- All tests pass (no skipped or disabled tests)
- Performance benchmarks met at each stage
- No breaking changes introduced (verified by integration tests)
- Code reviews completed before moving to next stage
- Git commits are clean and well-documented
- User can't tell anything changed (Stages 1-2)
- User sees new features work as expected (Stage 3-4)

**Warning signs:**

- Skipping tests "to save time"
- Moving to next stage with failing tests
- Performance degradation ignored
- Breaking changes found but not fixed
- Users reporting issues during testing
- Database corruption during testing
- Memory leaks or crashes

______________________________________________________________________

## Rollback Procedures

### Stage 1 Rollback

```bash
git revert <stage-1-commit>
rm pikaraoke/lib/karaoke_database.py
rm tests/test_karaoke_database.py
# No user impact - feature never integrated
```

### Stage 2 Rollback

```bash
git revert <stage-2-commit>
# Restore karaoke.py to previous version
# Database file remains but is unused
# Users see no change (back to pre-integration behavior)
```

### Stage 3 Rollback

```bash
git revert <stage-3-commit>
# Restore info.html and routes.py
# Database continues working in background
# Users lose admin UI but core functionality intact
```

### Stage 4 Rollback

```bash
git revert <stage-4-commit>
# Stop enrichment worker
# Database continues working for file tracking
# Users lose metadata enrichment but everything else works
```

______________________________________________________________________

## Final Notes

- **Take your time** - Rushing leads to bugs
- **Test thoroughly** - Each validation checkpoint is critical
- **Document as you go** - Update docs when behavior changes
- **Communicate progress** - Keep stakeholders informed
- **Ask for help** - Review planning docs if unclear
- **Celebrate milestones** - Recognize completion of each stage

**Remember:** The staged approach is designed to minimize risk. Each stage adds value independently, and rollback is always possible.

______________________________________________________________________

**Document Status:**  Complete
**Last Updated:** 2026-01-09
**Next Step:** Begin Stage 1 - Step 1.1 (Create karaoke_database.py)
