# Implementation Order & Dependencies

**Purpose:** Step-by-step implementation sequence with validation checkpoints.

**Key Principle:** Each stage builds on previous stages. Validate thoroughly before proceeding.

## Pre-Implementation Checklist

- \[ \] All planning documents reviewed and approved
- \[ \] Development environment set up
- \[ \] Git branch created: `feature/sqlite-database-upgrade`
- \[ \] Backup of current codebase taken
- \[ \] Test environment available

## Stage 1: Core Database Layer

**Goal:** Create and validate database module in isolation.

**Implementation Order:**

1. Create [pikaraoke/lib/karaoke_database.py](../../pikaraoke/lib/karaoke_database.py)
2. Implement core methods in order:
   - `__init__()` - Database initialization with WAL mode
   - `_create_schema()` - Create tables and indexes
   - `_generate_file_hash()` - SHA256 hash generation
   - `_detect_format()` - File type detection with CDG/ASS pairing
   - `scan_library()` - Full library scan with add/move/delete detection
   - `create_backup_file()` - SQLite backup API
   - `restore_from_file()` - Safe database replacement
   - `check_integrity()` - Database health validation
3. Create comprehensive unit tests in [tests/test_karaoke_database.py](../../tests/test_karaoke_database.py)

**Validation Checkpoint:**

- \[ \] All unit tests pass
- \[ \] Database file created with correct schema
- \[ \] Scan detects adds/moves/deletes correctly
- \[ \] Backup/restore works without data loss
- \[ \] CDG/ASS paired files handled correctly
- \[ \] Works with Unicode filenames

**Details:** See [stage1-core-database.md](stage1-core-database.md)

**Do NOT proceed to Stage 2 until all checkpoints pass.**

## Stage 2: Read-Only Integration

**Goal:** Integrate database into main app with zero breaking changes.

**Dependencies:** Stage 1 complete and validated.

**Implementation Order:**

1. Modify [pikaraoke/karaoke.py](../../pikaraoke/karaoke.py):
   - Import `KaraokeDatabase` in imports section
   - Initialize `self.db` in `__init__()` alongside existing `SongList`
   - Call `self.db.scan_library(self.download_path)` after download path setup
   - Populate `self.available_songs` from `self.db.get_all_song_paths()`
2. Test coexistence: Both `SongList` and `KaraokeDatabase` run in parallel

**Validation Checkpoint:**

- \[ \] App starts successfully
- \[ \] Browse page shows identical results to before
- \[ \] Search functionality unchanged
- \[ \] Queue management works
- \[ \] Database persists across restarts
- \[ \] Moved/renamed files detected on next startup
- \[ \] No performance regression (accept initial scan cost)

**Details:** See [stage2-app-integration.md](stage2-app-integration.md)

**Do NOT proceed to Stage 3 until behavior is 100% identical to pre-migration.**

## Stage 3: Admin UI

**Goal:** Expose database features through web interface.

**Dependencies:** Stage 2 complete and validated.

**Implementation Order:**

1. Create new Flask routes (or extend existing admin blueprint):
   - `POST /admin/sync_library` - Trigger manual scan
   - `GET /admin/download_backup` - Send backup file
   - `POST /admin/restore_backup` - Receive and restore backup
   - `GET /admin/library_stats` - Get library statistics
2. Modify [pikaraoke/templates/info.html](../../pikaraoke/templates/info.html):
   - Replace "Refresh Song List" section with "Manage Song Library"
   - Add "Synchronize Library" button
   - Add "Download Backup" button
   - Add "Restore Backup" file upload
   - Add confirmation dialogs for destructive operations
3. Add JavaScript handlers for AJAX interactions

**Validation Checkpoint:**

- \[ \] "Synchronize Library" triggers scan and shows stats
- \[ \] "Download Backup" generates valid .db file
- \[ \] "Restore Backup" replaces database successfully
- \[ \] All operations have proper error handling
- \[ \] Confirmation dialogs prevent accidental data loss
- \[ \] File upload validation works (size, extension)
- \[ \] Admin authentication enforced on all routes

**Details:** See [stage3-admin-ui.md](stage3-admin-ui.md)

**Do NOT proceed to Stage 4 until backup/restore workflow is fully tested.**

## Stage 4: Metadata Enrichment

**Goal:** Transform filenames into usable song metadata (artist, title, year, genre).

**Dependencies:** Stage 3 complete and validated.

**Note:** This stage is essential to achieve the core objective - moving from filename-based to metadata-based song management.

**Implementation Order:**

### Phase 4A: Filename Parsing (Required)

**Note:** YouTube IDs are already extracted during Stage 1 scan.

1. Add parsing functions to `KaraokeDatabase`:
   - `_parse_filename()` - Extract artist/title from patterns
   - `_detect_variant()` - Identify karaoke/live/acoustic variants
2. Call parsing during metadata enrichment to populate artist/title fields
3. `search_blob` already includes YouTube IDs from Stage 1

### Phase 4B: External API Enrichment (Enhances 4A)

1. Create background worker module for async enrichment
2. Implement Last.FM API integration with rate limiting
3. Add admin UI button to trigger metadata refresh
4. Add progress tracking for bulk operations

### Phase 4C: Manual Metadata Editor (Required)

1. Add edit metadata modal to browse UI
2. Create `POST /admin/update_song_metadata` route
3. Add bulk edit capabilities for corrections

**Validation Checkpoint:**

- \[ \] Filename parser extracts artist/title from common patterns
- \[ \] YouTube IDs already stored from Stage 1 scan
- \[ \] Enrichment is optional and non-blocking
- \[ \] Failed lookups handled gracefully
- \[ \] Manual editor saves changes correctly
- \[ \] Search includes metadata fields

**Details:** See [stage4-metadata-enrichment.md](stage4-metadata-enrichment.md)

## Dependency Graph

```
Stage 0 (Complete)
    |
    v
Stage 1: Core Database ──> Unit Tests Pass
    |
    v
Stage 2: Integration ──> Zero Breaking Changes Verified
    |
    v
Stage 3: Admin UI ──> Backup/Restore Tested
    |
    v
Stage 4: Metadata ──> Usable Song Data Achieved
    (4A + 4C Required, 4B Enhances)
```

## Critical Success Factors

**Stage 1:**

- Complete test coverage
- All edge cases handled
- Database operates correctly in isolation

**Stage 2:**

- Perfect backwards compatibility
- No user-visible changes
- Performance acceptable

**Stage 3:**

- Backup/restore workflow bulletproof
- Clear user feedback on all operations
- Security properly enforced

**Stage 4:**

- Filename parsing (4A) achieves usable metadata for most songs
- Manual editing (4C) handles edge cases and corrections
- External enrichment (4B) enhances quality but not required

## Rollback Procedures

If critical issues discovered at any stage:

**After Stage 1:** Delete `karaoke_database.py` and tests (no app impact)

**After Stage 2:** Remove DB initialization from `karaoke.py`, revert to pure `SongList`

**After Stage 3:** Remove admin UI additions, DB continues working in background

**After Stage 4:** Revert to basic filename display (metadata parsing disabled), DB still tracks files

## Testing Best Practices

**Unit Tests:**

- Test each method in isolation
- Mock file system operations where appropriate
- Test edge cases: empty dirs, permission errors, Unicode filenames

**Integration Tests:**

- Test full app workflow from startup to song playback
- Verify database persistence across restarts
- Test with realistic library sizes (1K, 5K, 10K songs)

**Manual Tests:**

- Test backup/restore with actual databases
- Verify UI responsiveness and error handling
- Test on multiple platforms (Windows, macOS, Linux, Raspberry Pi)

## Performance Targets

- Initial library scan: \< 15s for 1K songs
- Subsequent startups: \< 1s
- Browse page load: \< 1s
- Search response: \< 100ms
- Database file size: ~1-2KB per song

## Next Steps

1. Review this implementation order
2. Ensure all dependencies are clear
3. Begin Stage 1 implementation
4. Do not skip validation checkpoints
