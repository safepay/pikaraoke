# Stage 4: Background Worker & Confidence Scoring - Implementation Summary

**Created:** 2026-01-09
**Status:** ✅ Design Updated with Core Features

______________________________________________________________________

## Key Changes Made

### 1. Background Enrichment is NOW a Core Feature ⚡

**Previously:** Listed as "Improvement 2" (optional)
**Now:** PRIMARY implementation approach (mandatory)

**Why:**

- Last.FM rate limit: 5 req/sec = **720 songs/hour**
- MusicBrainz rate limit: 1 req/sec = **60 songs/hour**
- **10,000 songs = 4-14 hours** of API calls
- **Blocking the UI for hours is unacceptable**

**Solution:** Dedicated `EnrichmentWorker` thread that:

- ✅ Runs in background (daemon thread)
- ✅ Respects API rate limits
- ✅ Persists progress to database
- ✅ Survives app restarts
- ✅ Can be paused/resumed
- ✅ Provides real-time progress updates

______________________________________________________________________

### 2. Confidence Scoring is NOW Built-In

**Previously:** Listed as "Improvement 1" (optional)
**Now:** Core schema field with calculation logic

**Updated Schema:**

```sql
CREATE TABLE songs (
    ...
    confidence REAL DEFAULT 0.0,              -- NEW: Quality indicator
    metadata_status TEXT DEFAULT 'pending',   -- Enhanced states
    enrichment_attempts INTEGER DEFAULT 0,    -- NEW: Retry tracking
    last_enrichment_attempt TEXT,             -- NEW: Timestamp
    ...
);
```

**Confidence Levels:**

| Score | Status | Meaning | UI Indicator |
|-------|--------|---------|--------------|
| 1.00 | manual | User edited | 🟢 "Verified" |
| 0.90-0.99 | enriched | API + good filename match | 🟢 "High Confidence" |
| 0.70-0.89 | enriched | API but weak filename match | 🟡 "Medium Confidence" |
| 0.50-0.69 | parsed | Strong filename pattern | 🟡 "Parsed" |
| 0.30-0.49 | parsed | Weak filename pattern | 🟠 "Review Suggested" |
| 0.10-0.29 | parsed | Fallback (filename→title) | 🔴 "Low Confidence" |
| 0.00-0.09 | pending/failed | No metadata | 🔴 "Needs Review" |

______________________________________________________________________

### 3. New Database Tables

#### Enrichment Queue Table

```sql
CREATE TABLE enrichment_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    song_id INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    priority INTEGER DEFAULT 0,           -- Higher = process first
    queued_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(song_id)
);
```

**Purpose:** Track which songs need enrichment and in what order.

**Benefits:**

- Priority support (new uploads → high priority)
- Prevents duplicate processing
- Survives app restarts

#### Enrichment State Table

```sql
CREATE TABLE enrichment_state (
    key TEXT PRIMARY KEY,
    value TEXT
);
```

**Stores:**

- `worker_running` → 'true'/'false'
- `worker_paused` → 'true'/'false'
- `worker_started_at` → ISO timestamp
- `total_processed` → count
- `total_enriched` → count
- `total_failed` → count

**Purpose:** Persist worker state across app restarts.

______________________________________________________________________

## New Implementation Components

### 1. EnrichmentWorker Class

**File:** `pikaraoke/lib/enrichment_worker.py`

**Key Features:**

- Thread-safe (uses `threading.Event` for control)
- Rate-limited (configurable requests/second)
- Graceful shutdown (stop/pause/resume)
- Progress tracking (persistent + in-memory)
- Retry logic (max 3 attempts)
- Error handling (marks failed songs)

**Public API:**

```python
worker = EnrichmentWorker(db, api_key, rate_limit=5.0)
worker.start()  # Start processing
worker.pause()  # Pause (keeps thread alive)
worker.resume()  # Resume processing
worker.stop()  # Stop gracefully
progress = worker.get_progress()  # Get current stats
```

### 2. KaraokeDatabase Integration

**New Methods:**

```python
db.start_enrichment(api_key)  # Start background worker
db.stop_enrichment()  # Stop background worker
db.pause_enrichment()  # Pause worker
db.resume_enrichment()  # Resume worker
db.get_enrichment_progress()  # Get progress dict
db.queue_for_enrichment(song_ids)  # Add songs to queue
```

### 3. Admin UI - Enrichment Dashboard

**Location:** `pikaraoke/templates/info.html` (new section)

**Features:**

- Real-time progress bar
- Start/Stop/Pause buttons
- Statistics display (processed/enriched/failed)
- Estimated time remaining
- Auto-refresh via AJAX polling (every 2 seconds)

**UI Mock:**

```
┌───────────────────────────────────────────────────┐
│ 🎵 Metadata Enrichment                           │
├───────────────────────────────────────────────────┤
│                                                   │
│ Status: Running ⚡                                │
│ ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 247/1000 (24.7%) │
│                                                   │
│ Enriched: 180 | Failed: 67 | Remaining: 753     │
│ Est. Time: 2h 5m (at 5 req/sec)                  │
│                                                   │
│ [⏸ Pause] [⏹ Stop]                                │
│                                                   │
│ 💡 Tip: Enrichment runs in background.           │
│    You can use the app normally.                 │
└───────────────────────────────────────────────────┘
```

______________________________________________________________________

## Enrichment Flow

### Complete Pipeline

```
1. User scans library (Stage 2)
   ↓
2. Filenames parsed immediately (Phase 4A - synchronous)
   ↓ Songs have: artist, title, confidence=0.4-0.6
   ↓
3. Songs added to enrichment_queue
   ↓
4. Background worker starts automatically (or manually via UI)
   ↓
5. Worker processes queue at 5 req/sec (Last.FM limit)
   ↓ For each song:
   ├─ Query Last.FM API for (artist, title)
   ├─ If found: Update with year/genre/canonical names
   │            confidence → 0.70-0.99
   │            metadata_status → 'enriched'
   ├─ If not found: Mark as 'enrichment_failed'
   │                 confidence stays 0.4-0.6 (parsed)
   └─ Remove from queue
   ↓
6. User can browse/search during enrichment (non-blocking)
   ↓
7. Low-confidence songs flagged in UI for manual review
   ↓
8. User edits metadata manually (Phase 4C)
   ↓ confidence → 1.00 (manual)
   ↓ metadata_status → 'manual'
   ↓
9. Search/browse use enriched metadata
```

______________________________________________________________________

## Key Design Decisions

### Decision 1: Background Worker vs Celery/RQ

**Chosen:** Built-in Python `threading.Thread`

**Why:**

- ✅ No external dependencies (Celery requires Redis/RabbitMQ)
- ✅ Simpler setup for users
- ✅ Sufficient for single-instance apps
- ✅ State persists to SQLite (survives restarts)

**Trade-off:** Won't scale to multiple workers/machines (not needed for PiKaraoke)

### Decision 2: WAL Mode for Concurrency

**Chosen:** SQLite WAL mode (`PRAGMA journal_mode=WAL`)

**Why:**

- ✅ Allows concurrent reads while worker writes
- ✅ Better crash recovery
- ✅ Recommended for write-heavy workloads

**Result:** UI can browse songs while enrichment updates database.

### Decision 3: Queue-Based Processing

**Chosen:** Dedicated `enrichment_queue` table

**Why:**

- ✅ Priority support (new uploads first)
- ✅ Prevents duplicate processing
- ✅ Survives app restarts (queue persists)
- ✅ Can add manual re-queue feature

**Alternative:** Process all `metadata_status='parsed'` songs directly
**Problem:** Can't track priority, harder to resume after restart

### Decision 4: Retry Logic (Max 3 Attempts)

**Chosen:** Track `enrichment_attempts` per song

**Why:**

- ✅ Temporary API failures shouldn't permanently fail songs
- ✅ Prevents infinite retry loops
- ✅ After 3 failures → mark as 'enrichment_failed'

**User Override:** Failed songs can be manually edited or re-queued with high priority.

______________________________________________________________________

## Performance Analysis

### Enrichment Speed

| Library Size | Time (Last.FM) | Time (MusicBrainz) |
|--------------|----------------|-------------------|
| 100 songs    | 20 seconds     | 1.7 minutes       |
| 1,000 songs  | 3.3 minutes    | 16.7 minutes      |
| 10,000 songs | 33 minutes     | 2.8 hours         |

**Assumptions:**

- Last.FM: 5 req/sec = 300 req/min = 18,000 req/hour
- MusicBrainz: 1 req/sec = 60 req/min = 3,600 req/hour
- 100% success rate (real-world lower due to not-found)

### Memory Footprint

**Worker:** ~5-10 MB (lightweight)
**Database Growth:** ~2 KB per enriched song (year, genre, canonical names)
**Total Impact:** Negligible for typical libraries (\< 50 MB for 10K songs)

______________________________________________________________________

## Testing Strategy

### Unit Tests

```python
def test_enrichment_worker_starts():
    """Test worker thread starts and runs."""


def test_enrichment_worker_processes_queue():
    """Test worker dequeues and processes songs."""


def test_enrichment_worker_respects_rate_limit():
    """Test worker doesn't exceed API limits."""


def test_enrichment_worker_handles_api_failures():
    """Test worker marks failed songs correctly."""


def test_enrichment_worker_pause_resume():
    """Test pause/resume functionality."""


def test_enrichment_worker_survives_restart():
    """Test queue persists and resumes after restart."""


def test_confidence_calculation():
    """Test confidence scores are calculated correctly."""
```

### Integration Tests

```python
def test_full_enrichment_pipeline():
    """Test end-to-end enrichment flow."""
    # 1. Add songs to database
    # 2. Parse filenames
    # 3. Start enrichment worker
    # 4. Wait for completion
    # 5. Verify metadata updated
    # 6. Verify confidence scores assigned
```

### Manual Testing

- \[ \] Start enrichment, pause mid-way, resume
- \[ \] Start enrichment, restart app mid-way, verify resumes
- \[ \] Simulate API failures (disconnect network)
- \[ \] Test with 1K+ song library (real-world timing)
- \[ \] Verify UI stays responsive during enrichment
- \[ \] Test low-confidence song filtering in UI

______________________________________________________________________

## Migration Path from Reference Implementation

### Changes from database_upgrade.py

**Added:**

1. ✅ `confidence` field with calculation logic
2. ✅ `enrichment_attempts` and retry logic
3. ✅ `enrichment_queue` table
4. ✅ `enrichment_state` table
5. ✅ Background worker thread
6. ✅ Progress tracking
7. ✅ Pause/resume functionality

**Fixed:**

1. ✅ No longer blocks main thread
2. ✅ Rate limiting built-in
3. ✅ Survives app restarts
4. ✅ User-visible progress

**Preserved:**

1. ✅ Last.FM API integration approach
2. ✅ Filename parsing patterns
3. ✅ Metadata fields (artist, title, year, genre)

______________________________________________________________________

## User Experience Impact

### Before Stage 4

```
User adds 1000 songs
  ↓
App scans filenames (instant)
  ↓
Browse shows:
  - Artist: "Beatles" (from filename)
  - Title: "Hey Jude" (from filename)
  - Year: (empty)
  - Genre: (empty)
  - Confidence: 0.60 (yellow tag: "Parsed")
```

### After Stage 4

```
User adds 1000 songs
  ↓
App scans filenames (instant)
  ↓
Background enrichment starts automatically
  ↓ (User can browse/search immediately)
  ↓
3 minutes later (enrichment complete)
  ↓
Browse shows:
  - Artist: "The Beatles" (canonical from Last.FM)
  - Title: "Hey Jude"
  - Year: 1968 (from Last.FM)
  - Genre: "Rock" (from Last.FM)
  - Confidence: 0.95 (green tag: "High Confidence")

Low-confidence songs flagged:
  🟠 "Review Suggested" → User can manually edit
```

______________________________________________________________________

## API Key Management

### Configuration Options

**Option 1: Environment Variable (Recommended)**

```bash
export LASTFM_API_KEY="your_api_key_here"
```

**Option 2: Config File**

```ini
# config.ini
[API_KEYS]
lastfm = your_api_key_here
```

**Option 3: Admin UI**

```html
<div class="field">
    <label class="label">Last.FM API Key</label>
    <input class="input" type="text" name="lastfm_api_key"
           placeholder="Get key from https://www.last.fm/api">
    <p class="help">Required for metadata enrichment (genre, year)</p>
</div>
```

**Security:**

- Store in environment (not committed to git)
- Never log API keys
- Allow empty key (enrichment disabled gracefully)

______________________________________________________________________

## Success Criteria

### Functional

- \[ \] Background worker starts automatically after scan
- \[ \] Enrichment doesn't block UI
- \[ \] Progress bar updates every 2 seconds
- \[ \] Can pause/resume enrichment
- \[ \] Enrichment resumes after app restart
- \[ \] Failed songs marked correctly (max 3 retries)
- \[ \] Confidence scores calculated correctly

### Performance

- \[ \] Worker respects rate limit (no API bans)
- \[ \] Memory usage \< 50 MB for worker
- \[ \] UI responsive during enrichment
- \[ \] 1000 songs enriched in \< 5 minutes

### Quality

- \[ \] 60%+ songs enriched successfully
- \[ \] Confidence scores match data quality
- \[ \] Low-confidence songs flagged in UI
- \[ \] Manual edits override API data (confidence=1.0)

______________________________________________________________________

## Summary

### What Changed ✅

1. **Background worker** - Now CORE feature (was "improvement")
2. **Confidence scoring** - Now built into schema (was "improvement")
3. **Queue management** - New `enrichment_queue` table
4. **State persistence** - New `enrichment_state` table
5. **Progress tracking** - Real-time UI updates
6. **Retry logic** - Max 3 attempts per song

### Why It Matters 🎯

**Before:** Enrichment would block UI for hours
**After:** App usable immediately, enrichment in background

**Before:** No quality indicators
**After:** Confidence scores show data reliability

**Before:** Lost progress on restart
**After:** Resumes from where it left off

### Implementation Complexity 📊

| Component | Lines of Code | Complexity |
|-----------|---------------|------------|
| EnrichmentWorker | ~200 | Medium |
| DB Integration | ~50 | Low |
| Admin UI | ~100 | Low |
| Progress Polling | ~50 | Low |
| **Total** | **~400** | **Medium** |

**Estimated Effort:** 1-1.5 days (with testing)

______________________________________________________________________

## Next Steps

1. ✅ Review updated Stage 4 document
2. 📝 Approve background worker approach
3. 📝 Approve confidence scoring design
4. 🚀 Begin implementation (after Stages 1-3)

______________________________________________________________________

**Document Status:** ✅ Updated with Core Features
**Last Updated:** 2026-01-09
**Reviewed By:** Pending
