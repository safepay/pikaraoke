# PiKaraoke SQLite Database Migration

**Status:** Planning Complete - Ready for Stage 1 Implementation

## Overview

Migrate PiKaraoke from in-memory file scanning to persistent SQLite database with content fingerprinting, backup/restore, and library management.

**Key Benefits:**

- Persistent library (no rescanning on restart)
- Move/rename detection (files tracked by hash)
- Backup/restore capabilities
- Better search performance
- Metadata enrichment (artist, title, year, genre) - transforms filenames into usable song data

## Implementation Stages

| Stage | Name | Status | Dependencies |
|-------|------|--------|--------------|
| **1** | Core Database Layer | Next | - |
| **2** | Read-Only Integration | Planned | Stage 1 |
| **3** | Admin UI | Planned | Stage 2 |
| **4** | Metadata Enrichment | Planned | Stage 3 |

### Stage 1: Core Database Layer

**Deliverables:**

- [pikaraoke/lib/karaoke_database.py](../../pikaraoke/lib/karaoke_database.py) - `KaraokeDatabase` class
- [tests/test_karaoke_database.py](../../tests/test_karaoke_database.py) - Unit tests

**Key Features:**

- Schema with hash-based file tracking
- Scan library with add/move/delete detection
- Backup/restore using SQLite backup API
- CDG/ASS paired file handling
- WAL mode for crash safety

**Details:** See [stage1-core-database.md](stage1-core-database.md)

### Stage 2: Read-Only Integration

**Scope:**

- Initialize `KaraokeDatabase` in `Karaoke.__init__()`
- Populate existing `SongList` from database
- Zero breaking changes (coexistence strategy)

**Success Criteria:**

- App behavior identical to pre-migration
- Database persists across restarts
- No performance regression

**Details:** See [stage2-app-integration.md](stage2-app-integration.md)

### Stage 3: Admin UI

**Features:**

- Synchronize Library button (manual scan)
- Download Database Backup
- Restore Database from Backup

**Modified Files:**

- [pikaraoke/templates/info.html](../../pikaraoke/templates/info.html)
- Flask routes for admin operations

**Details:** See [stage3-admin-ui.md](stage3-admin-ui.md)

### Stage 4: Metadata Enrichment

**Goal:** Transform filenames into usable song metadata (artist, title, year, genre).

**Phases:**

- **4A:** Smart filename parsing (Artist - Title patterns) - Required
- **4B:** External API enrichment (Last.FM for year/genre) - Enhances 4A results
- **4C:** Manual metadata editor UI - Required for corrections

**Implementation:** 4A and 4C are required to achieve usable metadata. 4B enhances but is not essential.

**Details:** See [stage4-metadata-enrichment.md](stage4-metadata-enrichment.md)

## Naming Conventions

| Component | Value | Rationale |
|-----------|-------|-----------|
| Module | `karaoke_database.py` | Matches existing patterns |
| Class | `KaraokeDatabase` | Descriptive, PascalCase |
| Database file | `pikaraoke.db` | Stored in `get_data_directory()` |
| Backup pattern | `pikaraoke_backup_YYYYMMDD_HHMMSS.db` | Timestamped |
| Hash algorithm | SHA256 | Better collision resistance |
| Journal mode | WAL | Crash safety, concurrent reads |

## Implementation Order

See [implementation-order.md](implementation-order.md) for dependency flow and checkpoints.

## Rollback Strategy

Each stage can be rolled back independently:

**Stage 1:** Delete `karaoke_database.py` (no app impact)

**Stage 2:** Remove DB initialization, revert to `SongList`

**Stage 3:** Remove admin UI additions, DB continues working

**Stage 4:** Revert to basic filename display (metadata parsing disabled)

## Success Metrics

**Performance:**

- Startup time: ≤ previous + 2s (initial scan), ≤ 1s (subsequent)
- Search response: \< 100ms
- Scan time: \< 15s for 1K songs

**Reliability:**

- Zero data loss incidents
- 100% move/rename detection accuracy

**Usability:**

- Zero breaking changes (Stages 1-3)
- Intuitive admin features (no docs needed)
- Metadata quality: > 80% songs with accurate artist/title (Stage 4)

## Testing Strategy

**Unit Tests (Stage 1):**

- Database initialization, schema creation
- File scanning (adds/moves/deletes)
- Hash generation, backup/restore
- CDG/ASS pairing, edge cases

**Integration Tests (Stage 2):**

- App startup, browse/search functionality
- Queue operations, persistence across restarts

**Manual Tests (Stage 3):**

- Backup download/restore workflow
- Error handling, UI responsiveness

## Security Considerations

**Stage 3:**

- Admin authentication required for all routes
- File upload validation (extension, size, format)
- Path traversal prevention
- User-friendly error messages

**Stage 4:**

- API keys stored securely (environment variables)
- Rate limiting to prevent bans
- Response caching, error handling

## Quick Start

**For Implementers:**

1. Review this README
2. Read [stage1-core-database.md](stage1-core-database.md)
3. Implement Stage 1 with full test coverage
4. Validate before proceeding to Stage 2

**For Reviewers:**

1. Understand overall strategy (this document)
2. Review detailed stage plans
3. Validate success criteria are clear

**For Users:**
After deployment, you'll have persistent library, backup/restore, and rich metadata (artist, title, year, genre) instead of just filenames.
