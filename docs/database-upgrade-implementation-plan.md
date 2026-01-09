# Database Upgrade Implementation Plan

**Project:** PiKaraoke SQLite Database Migration
**Version:** 1.0
**Date:** 2026-01-09
**Status:** 📋 Planning Complete - Awaiting Stage 1 Approval

______________________________________________________________________

## Executive Summary

This document outlines the staged implementation plan for migrating PiKaraoke from an in-memory file scanning system to a persistent SQLite database with content fingerprinting, backup/restore capabilities, and enhanced library management.

### Key Objectives

1. **Zero Downtime Migration** - No breaking changes to existing functionality
2. **Data Safety** - Backup/restore capabilities for user libraries
3. **Performance** - Faster startup, better search, move/rename detection
4. **Maintainability** - Clean separation of concerns, testable components

### Staging Strategy

The implementation is divided into **4 distinct stages**, each with clear success criteria and the ability to pause/validate before proceeding:

| Stage | Name | Complexity | Risk | Dependencies |
|-------|------|------------|------|--------------|
| **0** | Context & Analysis | Low | None | ✅ Complete |
| **1** | Core Database Layer | Medium | Low | Stage 0 |
| **2** | Read-Only Integration | Medium | Low | Stage 1 |
| **3** | Admin UI - Library Management | High | Medium | Stage 2 |
| **4** | Metadata Enrichment | High | Medium | Stage 3 |

**Critical Success Factor:** Each stage must be fully validated before proceeding to the next.

______________________________________________________________________

## Naming Conventions

Based on analysis of existing codebase patterns:

### Database Module

- **File:** `pikaraoke/lib/karaoke_database.py`
- **Class:** `KaraokeDatabase`
- **Import:** `from pikaraoke.lib.karaoke_database import KaraokeDatabase`

### Database File

- **Filename:** `pikaraoke.db` (not a generic name)
- **Location:** `{get_data_directory()}/pikaraoke.db`
- **WAL Files:** `pikaraoke.db-wal`, `pikaraoke.db-shm` (auto-generated)

### Backup Files

- **Pattern:** `pikaraoke_backup_YYYYMMDD_HHMMSS.db`
- **Example:** `pikaraoke_backup_20260109_143022.db`

This follows the established pattern in the codebase:

- `download_manager.py` → `DownloadManager`
- `stream_manager.py` → `StreamManager`
- `song_list.py` → `SongList`
- `karaoke_database.py` → `KaraokeDatabase` ✅

______________________________________________________________________

## Stage Overview

### Stage 0: Context & Analysis ✅ COMPLETE

**Status:** Complete
**Document:** `docs/database-upgrade-stage0-analysis.md`

**Key Deliverables:**

- ✅ Analyzed existing codebase structure
- ✅ Identified storage locations
- ✅ Found and documented bugs in reference implementation
- ✅ Created integration strategy

______________________________________________________________________

### Stage 1: Core Database Layer

**Status:** 📋 Planned
**Document:** `docs/stage1-core-database.md`
**Estimated Complexity:** Medium
**Risk Level:** Low

**Scope:**

- Create `pikaraoke/lib/karaoke_database.py` with `KaraokeDatabase` class
- Implement library synchronization with move/rename detection
- Implement backup/restore using SQLite backup API
- Add database integrity checking
- Add development tooling for database inspection (optional, dev-only)

**Success Criteria:**

- \[ \] Database initializes with correct schema and WAL mode
- \[ \] `scan_library()` accurately detects adds/moves/deletes
- \[ \] `create_backup_file()` creates valid SQLite backup
- \[ \] `restore_from_file()` safely swaps database
- \[ \] `check_integrity()` validates database health
- \[ \] Unit tests pass for all edge cases
- \[ \] Handles CDG/ASS paired files correctly
- \[ \] Development database viewer accessible when `--dev-mode` flag is enabled

**Deliverables:**

1. `pikaraoke/lib/karaoke_database.py` - Main database class
2. Unit tests in `tests/test_karaoke_database.py`
3. Migration script for existing installations (if needed)
4. Development database viewer integration (dev-only feature)

**Development Tooling:**

To assist with database development, inspection, and debugging during Stages 1-4, a lightweight web-based SQLite viewer will be integrated:

- **Tool:** [sqlite-web](https://github.com/coleifer/sqlite-web)
- **Installation:** `uv add --dev sqlite-web`
- **Access:** Navigate to `http://localhost:5555/dev/database` when running with `--dev-mode` flag
- **Security:**
  - Only available when `--dev-mode` command-line flag is explicitly set
  - Protected by existing `@is_admin` decorator
  - Never deployed to production (flag not passed in release builds)
  - Can be configured as read-only or read-write based on development needs

**Features:**

- Execute SQL queries directly against the database
- Browse all tables and their contents
- Inspect schema and indexes
- View query execution plans
- Export data to CSV/JSON
- Monitor database statistics

**Implementation Example:**

```python
# In pikaraoke/app.py (or relevant initialization file)
if args.dev_mode:
    try:
        from sqlite_web import SqliteWebBlueprint

        db_path = os.path.join(get_data_directory(), "pikaraoke.db")
        db_blueprint = SqliteWebBlueprint(
            database=db_path,
            name="dev_database",
            read_only=False,  # Allow modifications during development
        )
        app.register_blueprint(db_blueprint, url_prefix="/dev/database")
        logger.info("Development database viewer enabled at /dev/database")
    except ImportError:
        logger.warning("sqlite-web not installed. Run: uv add --dev sqlite-web")
```

**Usage During Development:**

```bash
# Start PiKaraoke with development mode
python -m pikaraoke --dev-mode

# Access the database viewer
# Navigate to: http://localhost:5555/dev/database
```

**Note:** This development tool is designed to be removed before deployment by simply not passing the `--dev-mode` flag. It provides deep database inspection capabilities that complement the user-facing admin features planned for Stage 3.

**Pause Point:** Validate database operations in isolation before integrating into main app.

______________________________________________________________________

### Stage 2: Read-Only Integration

**Status:** 📋 Planned
**Document:** `docs/stage2-app-integration.md`
**Estimated Complexity:** Medium
**Risk Level:** Low

**Scope:**

- Initialize `KaraokeDatabase` in `Karaoke.__init__()`
- Run `scan_library()` on startup
- Populate existing `SongList` from database for backwards compatibility
- Validate that browse/search screens work identically

**Success Criteria:**

- \[ \] App starts successfully with database initialized
- \[ \] Browse page shows identical results to previous version
- \[ \] Search functionality works unchanged
- \[ \] Queue management works unchanged
- \[ \] No performance regression on startup (accept initial scan cost)
- \[ \] Database persists across restarts
- \[ \] Moved/renamed files detected correctly on next startup

**Key Integration Points:**

1. `pikaraoke/karaoke.py:299-301` - Initialize database alongside SongList
2. `pikaraoke/karaoke.py:577-579` - Modify `get_available_songs()`
3. No changes to Flask routes or templates (yet)

**Coexistence Strategy:**

```python
# Both systems run in parallel
self.available_songs = SongList()  # Legacy
self.db = KaraokeDatabase()  # New
self.db.scan_library(self.download_path)
# Populate legacy from new database
self.available_songs.update(self.db.get_all_song_paths())
```

**Pause Point:** Validate that app behavior is 100% identical to pre-migration state.

______________________________________________________________________

### Stage 3: Admin UI - Library Management

**Status:** 📋 Planned
**Document:** `docs/stage3-admin-ui.md`
**Estimated Complexity:** High
**Risk Level:** Medium

**Scope:**

- Replace "Refresh Song List" section with "Manage Song Library"
- Implement "Synchronize Library" feature
- Implement "Download Database Backup" feature
- Implement "Restore Database from Backup" feature
- Add appropriate warnings and confirmations

**Success Criteria:**

- \[ \] "Synchronize Library" button triggers scan and shows stats
- \[ \] "Download Backup" generates valid .db file
- \[ \] "Restore Backup" replaces database and prompts restart
- \[ \] All operations have proper error handling
- \[ \] User receives clear feedback on success/failure
- \[ \] Confirmation dialogs prevent accidental data loss

**Files Modified:**

1. `pikaraoke/templates/info.html` - Update admin UI section
2. Flask routes (create new blueprint or extend existing):
   - `admin.sync_library` - POST endpoint
   - `admin.download_backup` - GET endpoint (sends file)
   - `admin.upload_backup` - POST endpoint (receives file)

**UI Mock:**

```
┌─────────────────────────────────────────────────┐
│ ▼ Manage Song Library                          │
├─────────────────────────────────────────────────┤
│ Synchronize Library                            │
│ Scan for new, moved, or deleted files.         │
│ Last synced: 2026-01-09 14:30:22               │
│ [Synchronize Library]                          │
│                                                 │
│ Backup & Restore                               │
│ Download a snapshot of your song database.     │
│ [Download Database Backup]                     │
│                                                 │
│ Restore from a backup file:                    │
│ [Choose File] [Restore Database]               │
│ ⚠ This will overwrite your current library.    │
└─────────────────────────────────────────────────┘
```

**Pause Point:** Validate backup/restore workflow with test databases before enabling for users.

______________________________________________________________________

### Stage 4: Metadata Enrichment (Future)

**Status:** 📋 Planned
**Document:** `docs/stage4-metadata-enrichment.md`
**Estimated Complexity:** High
**Risk Level:** Medium

**Scope:**

- Implement smart filename parsing (artist/title extraction)
- Add Last.FM metadata lookup integration
- Create "Refresh Metadata" admin UI button
- Update browse/search UI to display year/genre if available

**Success Criteria:**

- \[ \] Filename parser extracts artist/title from common patterns
- \[ \] Last.FM API integration fetches year/genre/artwork
- \[ \] "Refresh Metadata" triggers background enrichment
- \[ \] UI displays metadata when available
- \[ \] Failed lookups are gracefully handled
- \[ \] Metadata enrichment is optional/non-blocking

**Phase 4A: Smart Parsing**

- Parse patterns like "Artist - Title.mp4"
- Extract YouTube IDs from filenames
- Populate `search_blob` for fast searching

**Phase 4B: External Enrichment**

- Last.FM API integration
- Rate limiting and retry logic
- Background worker for bulk enrichment

**Phase 4C: UI Updates**

- Display artist/title/year/genre in browse view
- Add "Browse by Artist" and "Browse by Genre" views
- Enhanced search with metadata filtering

**Pause Point:** This stage is optional and can be deferred to future releases.

______________________________________________________________________

## Risk Mitigation Strategies

### Risk: Database Corruption

**Likelihood:** Low
**Impact:** High
**Mitigation:**

- Use WAL mode for crash safety
- Implement `check_integrity()` on startup
- Automatic backup before restore operations
- Graceful degradation: fall back to file scan if DB corrupted

### Risk: Unicode Filename Issues

**Likelihood:** Medium (Windows)
**Impact:** Medium
**Mitigation:**

- Test with Japanese, Korean, Chinese, emoji filenames
- Use proper UTF-8 encoding throughout
- Handle Windows path encoding edge cases

### Risk: Large Library Performance

**Likelihood:** Medium (10K+ songs)
**Impact:** Medium
**Mitigation:**

- Add progress reporting for long scans
- Batch commits (every 100 songs)
- Consider background scanning with progress bar

### Risk: Breaking Changes

**Likelihood:** Low (due to coexistence strategy)
**Impact:** High
**Mitigation:**

- Keep `SongList` alongside database during Stages 1-3
- Extensive testing before removing legacy code
- Feature flag to disable database if needed

______________________________________________________________________

## Testing Strategy

### Unit Tests (Stage 1)

- Database initialization and schema creation
- File scanning with various formats (CDG, MP4, ZIP, etc.)
- Hash generation and collision handling
- Move/rename detection logic
- Backup/restore operations
- Edge cases: empty directories, permission errors, etc.

### Integration Tests (Stage 2)

- Full app startup with database
- Browse page rendering
- Search functionality
- Queue operations
- Persistence across restarts

### Manual Testing (Stage 3)

- Backup download in various browsers
- Restore upload with large databases
- Error handling (invalid files, disk full, etc.)
- UI responsiveness and feedback

### Performance Testing

- Scan time for 1K, 5K, 10K song libraries
- Database file size growth
- Query performance for search/browse
- Memory usage comparison vs. in-memory approach

______________________________________________________________________

## Rollback Plan

At each stage, if critical issues are discovered:

### Stage 1

- Delete `karaoke_database.py`
- No impact on existing app

### Stage 2

- Remove database initialization from `karaoke.py`
- Revert to pure `SongList` implementation
- Delete database file (user data not critical - can rescan)

### Stage 3

- Remove admin UI additions from `info.html`
- Remove new Flask routes
- Database still works for read-only in background

### Stage 4

- Disable metadata enrichment
- Database continues to work for file tracking

______________________________________________________________________

## Success Metrics

### Performance

- **Target:** Startup time ≤ previous version + 2 seconds (for initial scan)
- **Target:** Subsequent startups ≤ 1 second (database read)
- **Target:** Search response time ≤ 100ms

### Reliability

- **Target:** Zero data loss incidents
- **Target:** 100% move/rename detection accuracy
- **Target:** Backup/restore success rate > 99%

### Usability

- **Target:** Zero breaking changes to user workflows
- **Target:** Admin features intuitive (no documentation needed)
- **Target:** Clear error messages for all failure modes

______________________________________________________________________

## Timeline & Dependencies

```
Stage 0 (Complete) ──→ Stage 1 (Core DB) ──→ Stage 2 (Integration) ──→ Stage 3 (Admin UI) ──→ Stage 4 (Metadata)
     ✅                    [NEXT]                  [Blocked]              [Blocked]            [Optional]
```

**Critical Path:**

- Stages 0-3 must be completed in sequence
- Stage 4 can be deferred to future release
- Each stage requires validation before proceeding

**Estimated Effort:**

- Stage 1: 1-2 days (implementation + testing)
- Stage 2: 0.5-1 day (integration + validation)
- Stage 3: 1-2 days (UI + backend routes + testing)
- Stage 4: 2-3 days (parsing + API + UI)

**Total:** ~5-8 days of development + testing

______________________________________________________________________

## Appendix: File Checklist

### New Files

- \[ \] `pikaraoke/lib/karaoke_database.py` - Main database class
- \[ \] `tests/test_karaoke_database.py` - Unit tests
- \[ \] `docs/stage1-core-database.md` - Detailed Stage 1 plan
- \[ \] `docs/stage2-app-integration.md` - Detailed Stage 2 plan
- \[ \] `docs/stage3-admin-ui.md` - Detailed Stage 3 plan
- \[ \] `docs/stage4-metadata-enrichment.md` - Detailed Stage 4 plan

### Modified Files

- \[ \] `pikaraoke/app.py` - Development database viewer integration (Stage 1)
- \[ \] `pikaraoke/lib/args.py` - Add `--dev-mode` flag (Stage 1)
- \[ \] `pyproject.toml` - Add `sqlite-web` as dev dependency (Stage 1)
- \[ \] `pikaraoke/karaoke.py` - Database initialization (Stage 2)
- \[ \] `pikaraoke/templates/info.html` - Admin UI updates (Stage 3)
- \[ \] Flask routes file - New admin endpoints (Stage 3)
- \[ \] Browse/search templates - Metadata display (Stage 4)

### Generated Files (Runtime)

- `{get_data_directory()}/pikaraoke.db` - Main database
- `{get_data_directory()}/backups/*.db` - Backup snapshots

### Development-Only Files (Not Deployed)

- Development database viewer accessible at `/dev/database` (when `--dev-mode` is enabled)

______________________________________________________________________

## Next Steps

1. ✅ Review and approve this implementation plan
2. 📝 Create detailed Stage 1 planning document
3. 📝 Create detailed Stage 2 planning document
4. 📝 Create detailed Stage 3 planning document
5. 📝 Create detailed Stage 4 planning document (optional)
6. 🚀 Begin Stage 1 implementation

**Awaiting:** User approval to proceed with detailed stage planning documents.

______________________________________________________________________

**Document Status:** Updated with Development Tooling
**Last Updated:** 2026-01-09
**Last Change:** Added sqlite-web development database viewer for Stage 1
**Next Review:** After user feedback
