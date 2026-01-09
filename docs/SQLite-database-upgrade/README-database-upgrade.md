# PiKaraoke Database Upgrade - Documentation Index

**Project:** SQLite Database Migration for PiKaraoke
**Status:**  Planning Complete - Ready for Stage 1 Implementation
**Last Updated:** 2026-01-09

______________________________________________________________________

## Documentation Overview

This directory contains the complete planning documentation for migrating PiKaraoke from an in-memory file scanning system to a persistent SQLite database with metadata enrichment and library management features.

______________________________________________________________________

## Document Index

### 1. Master Implementation Plan

**File:** [database-upgrade-implementation-plan.md](database-upgrade-implementation-plan.md)

**Purpose:** Executive summary and overall project plan

**Contents:**

- Project overview and objectives
- Naming conventions (KaraokeDatabase, pikaraoke.db)
- High-level stage breakdown
- Risk assessment and mitigation
- Success metrics
- Timeline and dependencies

**Read this first** to understand the overall approach.

______________________________________________________________________

### 2. Stage 0: Context & Analysis  COMPLETE

**File:** [database-upgrade-stage0-analysis.md](database-upgrade-stage0-analysis.md)

**Purpose:** Codebase analysis and architectural decisions

**Contents:**

- Database class location decision (pikaraoke/lib/karaoke_database.py)
- Current implementation analysis (SongList class)
- Storage location planning (get_data_directory())
- Critical bugs found in reference implementation
- Admin UI location analysis (info.html)
- Integration strategy

**Status:**  Complete - Decisions finalized

______________________________________________________________________

### 3. Stage 1: Core Database Layer  NEXT

**File:** [stage1-core-database.md](stage1-core-database.md)

**Purpose:** Detailed implementation plan for the database module

**Contents:**

- KaraokeDatabase class design
- Schema design (songs, metadata tables)
- File format detection logic (CDG, ASS pairing)
- Hash generation (SHA256)
- Scan library algorithm (fixed from reference)
- Backup/restore implementation
- Integrity checking
- Unit testing plan

**Deliverables:**

- `pikaraoke/lib/karaoke_database.py`
- `tests/test_karaoke_database.py`

**Estimated Effort:** 1-2 days

______________________________________________________________________

### 4. Stage 2: Read-Only Integration

**File:** [stage2-app-integration.md](stage2-app-integration.md)

**Purpose:** Integration into main app with zero breaking changes

**Contents:**

- Coexistence strategy (DB + SongList in parallel)
- Karaoke.__init__() modifications
- Validation checklist (functional, performance, data)
- Testing procedures
- Rollback plan
- Performance benchmarks

**Key Principle:** 100% backwards compatible - users notice no difference

**Estimated Effort:** 0.5-1 day

______________________________________________________________________

### 5. Stage 3: Admin UI - Library Management

**File:** [stage3-admin-ui.md](stage3-admin-ui.md)

**Purpose:** Expose database features through web interface

**Contents:**

- UI design mockups
- Flask route implementations
  - `/admin/sync_library` - Manual synchronization
  - `/admin/download_backup` - Export database
  - `/admin/restore_backup` - Import database
  - `/admin/library_stats` - Get statistics
- Template modifications (info.html)
- JavaScript implementation
- Security considerations (auth, file upload validation)
- Testing plan

**Features:**

- Library status display
- Synchronize library button
- Download/restore backup functionality

**Estimated Effort:** 1-2 days

______________________________________________________________________

### 6. Stage 4: Metadata Enrichment (Optional)

**File:** [stage4-metadata-enrichment.md](stage4-metadata-enrichment.md)

**Purpose:** Advanced metadata features (artist, year, genre)

**Contents:**

#### Phase 4A: Smart Filename Parsing  RECOMMENDED

- Pattern-based extraction (Artist - Title, etc.)
- YouTube ID detection
- Variant detection (Karaoke, Live, etc.)
- Fast, offline, no dependencies

#### Phase 4B: External API Enrichment (Optional)

- Last.FM API integration
- Year/genre lookup
- Background worker with progress
- Caching layer
- Rate limiting

#### Phase 4C: Manual UI Editor (Essential Fallback)

- Edit metadata modal
- Bulk edit operations
- Reset to filename parsing

**Recommended Approach:**

1. Start with Phase 4A (filename parsing) - Gets 80% of value
2. Add Phase 4C (manual editor) - Handles edge cases
3. Defer Phase 4B (external API) - Only if users demand it

**Estimated Effort:** 2-3 days (all phases)

______________________________________________________________________

## Implementation Roadmap

```
Stage 0: Analysis >  COMPLETE

Stage 1: Core Database >  NEXT

          Create karaoke_database.py
          Implement scan/backup/restore
          Write unit tests
          Validate in isolation

Stage 2: Integration >  PLANNED

          Initialize DB in Karaoke.__init__()
          Populate SongList from DB
          Test browse/search/queue
          Validate 100% compatibility

Stage 3: Admin UI >  PLANNED

          Create Flask routes
          Update info.html template
          Add JavaScript handlers
          Test backup/restore workflow
          Security audit

Stage 4: Metadata (Optional) >  PLANNED

          Phase 4A: Filename parsing
          Phase 4C: Manual editor UI
          Phase 4B: External APIs (defer)
```

______________________________________________________________________

## Quick Start Guide

### For Reviewers

1. Read [database-upgrade-implementation-plan.md](database-upgrade-implementation-plan.md) - Get overview
2. Read [database-upgrade-stage0-analysis.md](database-upgrade-stage0-analysis.md) - Understand decisions
3. Review [stage1-core-database.md](stage1-core-database.md) - Next implementation step

### For Implementers

1. Start with **Stage 1** - Build the database layer
2. Run unit tests - Ensure quality
3. Proceed to **Stage 2** - Integrate into app
4. Validate thoroughly - No breaking changes
5. Implement **Stage 3** - Add admin UI
6. (Optional) **Stage 4** - Metadata enrichment

### For Users

After deployment, you'll gain:

- Persistent song library (no rescanning on restart)
- Move/rename detection (songs don't disappear when files move)
- Backup/restore (export your library for safekeeping)
- Better search (full-text search across metadata)
- (Optional) Rich metadata (artist, year, genre)

______________________________________________________________________

## Key Decisions Summary

| Decision | Resolution | Rationale |
|----------|-----------|-----------|
| **Module name** | `karaoke_database.py` | Matches existing naming convention |
| **Class name** | `KaraokeDatabase` | Descriptive, follows PascalCase pattern |
| **Database file** | `pikaraoke.db` | Descriptive, not generic |
| **Storage location** | `{get_data_directory()}/pikaraoke.db` | Platform-aware, existing utility |
| **Backup location** | `{get_data_directory()}/backups/` | Organized, separate from main DB |
| **Hash algorithm** | SHA256 | Better collision resistance than MD5 |
| **Journal mode** | WAL (Write-Ahead Logging) | Crash safety, concurrent reads |
| **Migration strategy** | Coexistence (DB + SongList) | Zero breaking changes |
| **Metadata approach** | Filename parsing -> External API -> Manual | Progressive enhancement |

______________________________________________________________________

## Critical Bugs Fixed

The reference implementation (`database_upgrade.py`) had several critical bugs that have been identified and fixed in the planning documents:

1. **Incomplete deletion logic** - Files without hashes were never cleaned up
2. **No CDG cleanup** - Deleting .mp3 left orphaned .cdg files
3. **Missing search index** - `search_blob` field defined but never populated
4. **Platform compatibility** - Hardcoded paths instead of using `get_data_directory()`
5. **No metadata tracking** - No `last_scan` timestamp

All fixes are incorporated into Stage 1 implementation plan.

______________________________________________________________________

## Testing Strategy

### Unit Tests (Stage 1)

- Database initialization
- Schema creation
- File scanning (adds/moves/deletes)
- Hash generation
- Backup/restore
- CDG/ASS pairing
- Edge cases (Unicode, permissions, etc.)

### Integration Tests (Stage 2)

- App startup
- Browse/search functionality
- Queue operations
- Persistence across restarts
- Move detection

### Manual Tests (Stage 3)

- Backup download
- Restore upload
- Synchronize library
- Error handling
- Mobile responsiveness

### Performance Benchmarks

- Scan time: \< 15s for 1K songs
- Startup time: \< 5s after initial scan
- Browse page: \< 1s load time
- Search response: \< 500ms

______________________________________________________________________

## Security Considerations

### Stage 3 (Admin UI)

- Admin authentication required for all routes
- File upload validation (extension, size, format)
- Path traversal prevention (`secure_filename`)
- CSRF protection
- User-friendly error messages (no technical details exposed)

### Stage 4 (External APIs)

- API key stored securely (environment variable)
- Rate limiting to prevent bans
- Response caching to reduce API calls
- Error handling for API failures

______________________________________________________________________

## Deployment Checklist

### Pre-Stage 1

- \[x\] Planning documents reviewed
- \[ \] Team approval received
- \[ \] Development environment ready

### Pre-Stage 2

- \[ \] Stage 1 unit tests pass
- \[ \] Code review completed
- \[ \] Performance benchmarks met

### Pre-Stage 3

- \[ \] Stage 2 integration tests pass
- \[ \] Zero breaking changes verified
- \[ \] User acceptance testing complete

### Pre-Stage 4

- \[ \] Stage 3 security audit passed
- \[ \] Backup/restore workflow validated
- \[ \] User documentation published

______________________________________________________________________

## Success Metrics

### Technical Metrics

- **Startup time:** ≤ previous + 2s (initial scan), ≤ 1s (subsequent)
- **Search performance:** \< 100ms response time
- **Data integrity:** 100% move/rename detection accuracy
- **Reliability:** Zero data loss incidents

### User Experience Metrics

- **Breaking changes:** 0 (Stages 2-3)
- **User complaints:** 0 about performance regression
- **Feature adoption:** > 50% of admins use backup/restore
- **Manual edit usage:** \< 20% of songs (indicates good auto-parsing)

______________________________________________________________________

## Rollback Strategy

Each stage has a documented rollback plan:

### Stage 1

- Delete `karaoke_database.py` (no impact on app)

### Stage 2

- Remove DB initialization from `karaoke.py`
- Revert to pure `SongList` implementation

### Stage 3

- Remove admin UI additions
- Remove Flask routes
- Database continues working in background

### Stage 4

- Disable metadata enrichment
- Database still works for file tracking

**Key Principle:** Each stage can be rolled back independently without data loss.

______________________________________________________________________

## Support & Questions

### During Planning Phase

- Review documents and provide feedback
- Ask questions about approach
- Suggest improvements

### During Implementation

- Report bugs in GitHub issues
- Submit pull requests for fixes
- Update documentation as needed

### After Deployment

- Monitor logs for errors
- Collect user feedback
- Track performance metrics

______________________________________________________________________

## Lessons Learned (Post-Implementation)

*This section will be updated after each stage is completed*

### Stage 1

- TBD

### Stage 2

- TBD

### Stage 3

- TBD

### Stage 4

- TBD

______________________________________________________________________

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-01-09 | Initial planning documents created |
| | | - Master implementation plan |
| | | - Stage 0 analysis complete |
| | | - Stages 1-4 detailed plans created |
| | | - Naming conventions finalized |

______________________________________________________________________

## Related Documentation

- [PiKaraoke Main README](../README.md)
- [Contributing Guide](../CONTRIBUTING.md) *(if exists)*
- [Database Schema Reference](stage1-core-database.md#schema-design)
- [API Documentation](stage4-metadata-enrichment.md#external-api-enrichment)

______________________________________________________________________

**Status:**  Planning Complete - Awaiting Stage 1 Implementation
**Next Action:** Review and approve Stage 1 plan, then begin implementation
**Estimated Total Effort:** 5-8 days (Stages 1-4)
**Critical Path:** Stages 1 -> 2 -> 3 (Stage 4 optional)

______________________________________________________________________

*For questions or clarifications, please review the detailed stage documents or open a discussion.*
