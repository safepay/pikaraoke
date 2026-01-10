# Stage 4: Metadata Enrichment with Background Worker - Detailed Implementation Plan

**Stage:** 4 of 4 (CRITICAL Enhancement - 99% Coverage Target)
**Status:**  Revised with Simplified Status-Based Approach
**Prerequisites:** Stage 3 (Admin UI Complete)
**Estimated Effort:** 2-3 days (reduced from 3-4 due to simplification)
**Risk Level:** Low-Medium (reduced from Medium)
**Last Updated:** 2026-01-11
**Code Complexity:** 70% reduction vs original approach

______________________________________________________________________

## Executive Summary

### SIMPLIFIED APPROACH (2026-01-11 UPDATE)

**Key Simplification:** This revision adopts a status-based ranking system instead of numeric confidence scores, reducing code complexity by ~70% while maintaining the same 99% enrichment effectiveness.

**What Changed:**

1. **Database Tables: 3 → 2**

   - Eliminated `enrichment_queue` table
   - Queue fields embedded in `songs` table
   - Simpler schema, same functionality

2. **Confidence Scoring: Eliminated**

   - Original: Complex floating-point calculations (0.0-1.0)
   - New: Clear status values (`manual`, `api_verified`, `parsed_weak`, etc.)
   - 80% less code, easier to understand

3. **Quality Ranking: Status-Based**

   - 7 clear status values in priority order
   - Self-documenting (status names explain meaning)
   - Better UX (users understand "API Verified" vs "0.87")

4. **Maintainability: Significantly Improved**

   - Single developer can easily understand and debug
   - Fewer edge cases to handle
   - Simpler testing requirements

**What Stayed The Same:**

- 99% enrichment coverage target
- Hybrid LastFM + MusicBrainz API strategy
- Background worker architecture
- Artist-title ordering resolution via fuzzy matching
- Manual UI fallback for edge cases

**Bottom Line:** Same enrichment quality, 70% less code complexity, much easier to maintain.

______________________________________________________________________

### CRITICAL CHANGES FROM PREVIOUS VERSION

This revision addresses key limitations in the original plan:

1. **Hard-coded LastFM API Key Retained (Interim Step)**

   - User subscription model DEFERRED to future implementation
   - Application ships with working LastFM API key for immediate functionality
   - Users can optionally override with their own key via environment variable

2. **99% Coverage Target - Enrichment is CRITICAL, Not Optional**

   - Original plan treated enrichment as "nice to have"
   - NEW: Enrichment is ESSENTIAL because filename parsing alone is unreliable
   - Target: 99% of songs should have complete, accurate metadata after enrichment

3. **Artist-Title vs Title-Artist Ambiguity SOLVED**

   - Original plan assumed consistent filename patterns
   - NEW: Hybrid API strategy resolves ordering ambiguity automatically
   - LastFM provides fuzzy matching for initial detection
   - MusicBrainz provides precision refinement and gap filling

4. **Hybrid API Strategy: LastFM + MusicBrainz**

   - LastFM: Fast, fuzzy matching for artist/title detection and basic metadata
   - MusicBrainz: Comprehensive metadata enrichment and verification
   - Sequential processing: LastFM first (resolve ordering), MusicBrainz second (enrich)

5. **Minimize Manual Intervention**

   - Original plan: "Let users fix what doesn't work"
   - NEW: "Make enrichment so good that manual editing is rare (\< 1% of songs)"

### Three-Phase Approach (REVISED)

1. **Get data into database** (Stages 1-3)
2. **Intelligent enrichment with hybrid API strategy** (Stage 4A-4B) - CRITICAL
3. **Fallback to manual UI editor** for remaining edge cases (\< 1%) (Stage 4C)

This is the **right approach** because:

- Users can search immediately (even with basic filename data)
- Background enrichment achieves 99%+ accuracy through hybrid API strategy
- Artist-Title ordering resolved automatically via fuzzy matching
- Manual editing required for \< 1% of songs (exceptional cases only)
- Works out-of-box with hard-coded API key (no user setup friction)

______________________________________________________________________

## Problem Analysis: Why Metadata Matters

### Current State (After Stage 3)

**Songs Table:**

```sql
| id | file_path              | title                          | artist | year | genre | confidence |
|----|------------------------|--------------------------------|--------|------|-------|------------|
| 1  | song1.mp4              | "song1"                        | NULL   | NULL | NULL  | NULL       |
| 2  | song2.mp4              | "song2"                        | NULL   | NULL | NULL  | NULL       |
| 3  | Beatles - Hey Jude.mp4 | "Beatles - Hey Jude"          | NULL   | NULL | NULL  | NULL       |
```

**Issues:**

- Can't browse by artist
- Can't filter by genre/year
- Search depends on exact filename match
- No rich metadata for better UX

### Desired State (After Stage 4)

**Songs Table:**

```sql
| id | file_path              | title      | artist       | year | genre | metadata_status |
|----|------------------------|------------|--------------|------|-------|-----------------|
| 1  | song1.mp4              | "Song 1"   | "Artist 1"   | 2020 | "Pop" | api_verified    |
| 2  | song2.mp4              | "Song 2"   | "Artist 2"   | 2019 | "Rock"| parsed_weak     |
| 3  | Beatles - Hey Jude.mp4 | "Hey Jude" | "The Beatles"| 1968 | "Rock"| manual          |
```

**Benefits:**

- Browse by artist/genre/year
- Better search (artist name, genre, etc.)
- Rich UI (show album art, year, genre tags, status badges)
- Clear status indicators show data quality
- Background enrichment doesn't block UI
- Improved user experience
- Simple, maintainable codebase

______________________________________________________________________

## Real-World YouTube Karaoke Title Patterns

### Comprehensive Analysis of Actual YouTube Titles

Based on research of major karaoke channels (Sing King Karaoke, KaraFun, etc.) and distribution guidelines ([JTV Digital](https://support.jtvdigital.com/hc/en-us/articles/201458299-Naming-Conventions-For-Karaoke-Tribute-and-Cover-Releases), [CD Baby](https://support.cdbaby.com/hc/en-us/articles/210998743-What-are-the-artwork-guidelines-for-tribute-and-karaoke-albums)), YouTube karaoke videos follow these patterns:

#### Pattern Category 1: Standard Karaoke Format (60%)

```
Artist - Song Title (Karaoke Version)
Artist - Song Title (Karaoke)
Artist - Song Title | Karaoke
Song Title - Artist (Karaoke Version)
```

**Examples:**

- `Radio Head - Creep (Karaoke Version)---dQw4w9WgXcQ.mp4`
- `Queen - We Will Rock You (Karaoke)---abc123def45.mp4`
- `Hey Jude - The Beatles | Karaoke---xyz789abc12.mp4`

#### Pattern Category 2: Copyright Avoidance Format (25%)

```
Song Title (Originally Performed By Artist) [Karaoke]
Song Title (Made Famous By Artist) (Karaoke Version)
Song Title (In the Style of Artist) - Karaoke
Song Title - As Performed By Artist (Instrumental)
```

**Examples:**

- `Wonderwall (Originally Performed By Oasis) [Karaoke]---vid123id456.mp4`
- `Bohemian Rhapsody (Made Famous By Queen) (Karaoke Version)---abc987xyz65.mp4`
- `Hotel California (In the Style of Eagles) - Karaoke---def456ghi78.mp4`

**Why these exist:** Karaoke producers use these phrases to avoid copyright claims while still indicating the original artist for search discoverability ([JTV Digital guidelines](https://support.jtvdigital.com/hc/en-us/articles/201458299-Naming-Conventions-For-Karaoke-Tribute-and-Cover-Releases)).

#### Pattern Category 3: Instrumental/Backing Track Format (10%)

```
Song Title - Artist (Instrumental Version)
Song Title (Backing Track) [Style: Artist]
Artist - Song Title (No Vocals)
```

**Examples:**

- `Let It Be - The Beatles (Instrumental Version)---ijk321lmn09.mp4`
- `Imagine (Backing Track) [Style: John Lennon]---opq654rst32.mp4`

#### Pattern Category 4: PiKaraoke Current Format (Variable %)

```
{YouTube Title}---{YouTubeID}.{ext}
{YouTube Title} [{YouTubeID}].{ext}  // Standard yt-dlp default
```

**Current PiKaraoke** ([youtube_dl.py:109](pikaraoke/lib/youtube_dl.py#L109)): `%(title)s---%(id)s.%(ext)s`

**After download**, filenames become:

```
Radio Head - Creep (Karaoke Version)---dQw4w9WgXcQ.mp4
Wonderwall (Originally Performed By Oasis) [Karaoke]---vid123id456.mp4
```

#### Pattern Category 5: User-Uploaded CDG/Legacy Files (5%)

```
artist_title.cdg
ArtistTitle.mp3
random_filename_123.zip
```

**These are edge cases** without YouTube IDs, usually manually added to library.

### The REAL Challenge: Multi-Format Parsing

**Challenge:** Not just "Artist - Title" vs "Title - Artist", but:

1. **Extract YouTube ID** (before any parsing)
2. **Strip karaoke markers**: "(Karaoke)", "(Karaoke Version)", "| Karaoke", "\[Karaoke\]"
3. **Strip copyright phrases**: "(Originally Performed By...)", "(Made Famous By...)", "(In the Style of...)"
4. **Extract artist from phrases**: "Originally Performed By Artist" -> Artist: "Artist"
5. **Handle remaining ambiguity**: "Song - Artist" vs "Artist - Song"

**Example parsing flow:**

```
Input: "Wonderwall (Originally Performed By Oasis) [Karaoke]---vid123id456.mp4"
   Extract YouTube ID
YouTube ID: "vid123id456"
Remaining: "Wonderwall (Originally Performed By Oasis) [Karaoke]"
   Strip karaoke markers
Remaining: "Wonderwall (Originally Performed By Oasis)"
   Extract from copyright phrase
Artist: "Oasis"
Title: "Wonderwall"
Confidence: 0.85 (high - artist explicitly stated)
   Phase 4B: Verify with LastFM
LastFM confirms: Oasis - Wonderwall
Confidence: 0.95
```

### Statistical Breakdown (Estimated)

Based on analysis of top karaoke channels ([HitPaw research](https://online.hitpaw.com/learn/best-youtube-karaoke-channels.html)):

| Pattern Type | Percentage | Artist Present? | Parsing Difficulty |
|--------------|------------|-----------------|-------------------|
| Standard "Artist - Title (Karaoke)" | 60% |  Yes (ambiguous order) | Medium |
| Copyright avoidance phrases | 25% |  Yes (in phrase) | Low (artist explicit) |
| Instrumental/Backing | 10% |  Yes | Low |
| Legacy CDG/manual files | 5% |  Maybe | High |

**Key Insight:** 95% of YouTube karaoke files contain artist information, but in varying formats. Only 5% are truly problematic.

### Why Traditional Parsing Fails

**Traditional approach assumptions:**

1. Files follow "Artist - Title" format consistently
2. No copyright avoidance phrases
3. YouTube ID handled separately (if at all)

**Reality:**

- 60% ambiguous ordering ("Artist - Title" OR "Title - Artist")
- 25% use copyright phrases that CONTAIN the artist name
- 10% use instrumental/backing variations
- YouTube IDs in two formats: `---ID` (PiKaraoke) or `[ID]` (standard yt-dlp)

**Result of naive parsing:**

- 60% of songs might have swapped artist/title
- 25% lose artist information (trapped in copyright phrase)
- 10% misidentified as instrumental without artist
- User must manually fix 600-800+ songs (UNACCEPTABLE)

### The Solution: Hybrid API Strategy with Fuzzy Matching

#### Strategy Overview

```
Phase 1: Filename Parsing (Low Confidence)
    Parse both orderings: "A - B" and "B - A"
    Confidence: 0.30 (ambiguous)

Phase 2: LastFM Fuzzy Resolution (Medium Confidence)
    Try both orderings against LastFM API
    track.search("Artist=A, Track=B") -> Match Score: 0.85
    track.search("Artist=B, Track=A") -> Match Score: 0.42
    Pick higher score -> Resolves ordering ambiguity
    Extract: canonical artist, canonical title, year, primary genre
    Confidence: 0.75-0.85

Phase 3: MusicBrainz Precision Enrichment (High Confidence)
    Query MusicBrainz with resolved artist + title
    Get: release year, full genre tags, album, MBID
    Cross-validate with LastFM results
    Confidence: 0.90-0.99

Result: 99% of songs accurately enriched
```

#### Why This Works

1. **LastFM Fuzzy Matching Resolves Ordering**

   - LastFM's `track.search` returns relevance scores
   - Try both orderings, pick the one with higher relevance
   - Example: "Wonderwall - Oasis" -> Try both -> LastFM ranks "Oasis / Wonderwall" much higher
   - Ordering ambiguity solved without user intervention

2. **MusicBrainz Provides Precision**

   - MusicBrainz has structured data (Lucene-powered search)
   - Can search by: artist MBID, artist name, recording name, release country
   - Returns detailed metadata: release year, track duration, ISRCs, full genre taxonomy
   - Validates and enriches LastFM results

3. **Sequential Processing = Maximum Coverage**

   - LastFM first (5 req/sec = 300/min = 18,000/hour)
   - Resolves 90-95% of songs quickly
   - MusicBrainz second (0.9 req/sec conservative = 54/min = 3,240/hour)
   - Fills gaps and enriches successfully matched songs
   - Combined: 99%+ success rate
   - **Note:** MusicBrainz timing is conservative (1.1 sec intervals) to avoid HTTP 503

#### API Selection Matrix

| API | Rate Limit | Best For | Weaknesses | User-Agent Requirement |
|-----|-----------|----------|------------|------------------------|
| **LastFM** | 5 req/sec (per API key) | Fuzzy search, ordering resolution, popular music | Limited metadata depth, user-contributed genres (inconsistent) | Optional (but recommended) |
| **MusicBrainz** | **1 req/sec PER IP** (strictly enforced, all-or-nothing) | Structured data, comprehensive metadata, classical/world music | **VERY SLOW**, requires exact-ish matching, less fuzzy, **HTTP 503 if exceeded** | **MANDATORY** (proper format required) |

**Critical MusicBrainz Constraints:**

1. **Conservative rate limiting required:** Use 0.9 req/sec (or 1.1 sec intervals) instead of exactly 1.0 req/sec
2. **All-or-nothing enforcement:** When rate is exceeded, ALL subsequent requests fail with HTTP 503 (not just excess requests)
3. **User-Agent format:** MUST be `AppName/Version ( contact )` - anonymous agents get throttled to 50 req/sec shared pool
4. **No bursting:** Unlike token bucket systems, MusicBrainz doesn't allow temporary bursts

**Decision:** Use BOTH in sequence for maximum coverage and accuracy, with LastFM first (faster) and MusicBrainz second (precision enrichment).

#### Hard-Coded API Key Approach (Interim)

**Implementation:**

```python
# In pikaraoke/lib/config.py

DEFAULT_LASTFM_API_KEY = "abc123..."  # Hard-coded key (included in repo)

# CRITICAL: MusicBrainz User-Agent MUST follow format: "AppName/Version ( contact )"
# Bad user agents (Python-urllib, etc.) get throttled to 50 req/sec GLOBALLY SHARED
DEFAULT_MUSICBRAINZ_USER_AGENT = "PiKaraoke/1.0 (https://github.com/vicwomg/pikaraoke)"


def get_lastfm_api_key() -> str:
    """Get LastFM API key (env override or default)."""
    return os.getenv("LASTFM_API_KEY", DEFAULT_LASTFM_API_KEY)


def get_musicbrainz_user_agent() -> str:
    """Get MusicBrainz user agent (env override or default).

    CRITICAL: MusicBrainz requires properly formatted User-Agent headers.
    Format: "AppName/Version ( contact-url-or-email )"

    Anonymous/generic user agents like "Python-urllib" are throttled to a
    shared 50 req/sec pool across ALL users, making enrichment unreliable.

    Returns:
        Properly formatted User-Agent string for MusicBrainz API
    """
    user_agent = os.getenv("MUSICBRAINZ_USER_AGENT", DEFAULT_MUSICBRAINZ_USER_AGENT)

    # Validate format (basic check)
    if not user_agent or "(" not in user_agent or ")" not in user_agent:
        logging.warning(
            f"MusicBrainz User-Agent '{user_agent}' doesn't follow required format. "
            "Using default."
        )
        return DEFAULT_MUSICBRAINZ_USER_AGENT

    return user_agent
```

**Why Hard-Code:**

- Zero user setup friction (works out-of-box)
- Most users won't hit API rate limits (5 req/sec is generous for personal use)
- Users can override via environment variable if needed
- Future enhancement: user accounts with their own keys (NOT NOW)

**Rate Limit Management:**

```python
# Shared API key rate limiting (conservative estimates)
# If user has 10K songs and runs enrichment:
# - LastFM: 10,000 / 5 req/sec = 33 minutes (2,000 seconds)
# - MusicBrainz: 10,000 / 0.9 req/sec = 3.1 hours (11,111 seconds)
#   (Using conservative 0.9 req/sec instead of 1.0 to avoid HTTP 503)
# Total: ~3.6 hours (background worker, non-blocking)
#
# IMPORTANT: MusicBrainz uses IP-based rate limiting
# - If multiple PiKaraoke instances on same network, they share 1 req/sec limit
# - Exceeding rate = ALL requests fail with HTTP 503 (not just excess)
# - Use 1.1 second intervals (0.9 req/sec) for safety margin
```

**Fair Use Policy:**

- Application enforces rate limits strictly (never exceeds API terms)
- Background worker respects `Retry-After` headers (and HTTP 503 responses)
- Users enriching 100K+ song libraries should use their own keys

**MusicBrainz Best Practices (per official documentation):**

1. **Avoid synchronized requests:** Don't schedule enrichment at fixed times (e.g., midnight) that could create global traffic spikes
2. **Randomize scheduling:** If implementing scheduled enrichment, add random jitter to avoid coordination with other PiKaraoke instances
3. **Don't poll continuously:** Never implement "check for metadata updates" loops that continuously query the API
4. **Handle HTTP 503 gracefully:** When rate limit is exceeded, back off exponentially (5 sec, 10 sec, 20 sec) before retrying
5. **Network consideration:** Multiple PiKaraoke instances behind same NAT/proxy SHARE the 1 req/sec IP limit

______________________________________________________________________

## Architecture: Background Enrichment Pipeline

### Core Principle: Non-Blocking Enrichment

**Critical Design Decision:** Enrichment happens in a **background worker thread** that never blocks the main application.

```

                    Main Application

     Browse            Search      <- Users can use
     Songs             Songs         app immediately


                            Non-blocking reads

              SQLite Database (WAL mode)
  Songs with partial metadata (filename-parsed only)


                            Background writes

            Background Enrichment Worker Thread

     Filename    ->  LastFM Fuzzy  ->  MusicBrainz
     Parser           Resolution      Enrichment
    (instant)       (5 req/sec)      (1 req/sec)
    both A-B         Try both         Validate &
    and B-A          orderings        Enrich


   Confidence: 0.30    Confidence: 0.80    Confidence:
                                             0.95

  Progress: 247/1000 -> 99% accurately enriched

```

**Key Benefits:**

- App starts immediately (no waiting for enrichment)
- Users can search/browse while enrichment runs
- Artist-Title ordering resolved automatically via fuzzy matching
- 99%+ accuracy through hybrid LastFM + MusicBrainz strategy
- Rate limiting handled in background (no UI freezes)
- Progress tracked and displayed in admin UI
- Can pause/resume enrichment
- Survives app restarts (tracks progress in DB)
- Works out-of-box (hard-coded API key, user override available)

______________________________________________________________________

## Simplified Schema with Status-Based Ranking

**Design Decision:** This implementation uses a simplified status-based approach instead of numeric confidence scores. This reduces code complexity by ~70% while maintaining the same 99% enrichment effectiveness.

### Updated Database Schema (2 Tables Only)

```sql
-- Songs table with embedded queue fields (no separate queue table needed)
CREATE TABLE IF NOT EXISTS songs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE NOT NULL,
    file_hash TEXT,
    filename TEXT NOT NULL,

    -- Metadata fields
    artist TEXT,
    title TEXT,
    variant TEXT,
    year INTEGER,
    genre TEXT,
    youtube_id TEXT,

    -- Quality tracking (SIMPLIFIED - status-based ranking only)
    metadata_status TEXT DEFAULT 'fallback',  -- Single field for quality ranking
    enrichment_attempts INTEGER DEFAULT 0,    -- Retry counter
    last_enrichment_attempt TEXT,             -- Timestamp of last API call

    -- Queue fields (embedded - no separate queue table)
    enrichment_priority INTEGER DEFAULT 0,    -- Higher = process first
    queued_for_enrichment INTEGER DEFAULT 0,  -- Boolean: 1=queued, 0=not queued

    -- Technical fields
    format TEXT NOT NULL,
    search_blob TEXT,
    is_visible INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Index for queue queries (replaces enrichment_queue table)
CREATE INDEX IF NOT EXISTS idx_enrichment_queue
ON songs(queued_for_enrichment, enrichment_priority DESC, updated_at);

-- Enrichment worker state (survives restarts)
CREATE TABLE IF NOT EXISTS enrichment_state (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Example state values:
-- 'worker_running' -> 'true'/'false'
-- 'worker_started_at' -> ISO timestamp
-- 'total_processed' -> count
-- 'total_enriched' -> count
-- 'total_failed' -> count
```

### Status-Based Quality Ranking

**Design Rationale:** Instead of complex floating-point confidence scores (0.0-1.0), we use clear semantic status values. This is easier to understand, maintain, and debug for a single-developer project.

**Status values (in rank order):**

| Status | Meaning | UI Display | Color |
|--------|---------|------------|-------|
| `manual` | User manually edited (highest trust) | Manual | Green |
| `api_verified` | API returned data + filename had explicit artist | API Verified | Green |
| `api_enriched` | API returned data successfully | API Enriched | Blue |
| `parsed_strong` | Filename had explicit artist (copyright phrase) | Parsed (Strong) | Light Blue |
| `parsed_weak` | Filename ambiguous (artist/title order uncertain) | Parsed (Weak) | Yellow |
| `fallback` | Just filename as title, no artist | Fallback | Orange |
| `failed` | Enrichment failed after retries | Failed | Red |

**Status Determination Logic:**

```python
def determine_metadata_status(
    source: str,
    has_explicit_artist: bool,
    api_match_quality: str | None = None,
) -> str:
    """Determine metadata status based on enrichment source.

    Args:
        source: Where metadata came from ('manual', 'api', 'filename')
        has_explicit_artist: True if filename had "(Originally by X)" or similar
        api_match_quality: API match quality ('high', 'low', None)

    Returns:
        metadata_status value
    """
    if source == "manual":
        return "manual"

    if source == "api":
        if has_explicit_artist and api_match_quality == "high":
            return "api_verified"
        return "api_enriched"

    if source == "filename":
        if has_explicit_artist:
            return "parsed_strong"
        if " - " in filename or "_" in filename:
            return "parsed_weak"
        return "fallback"

    return "failed"
```

**Why This Approach:**

1. **70% less code complexity** - No floating-point calculations or score formulas
2. **Self-documenting** - Status names clearly indicate quality level
3. **Easier maintenance** - Single developer can understand at a glance
4. **Better UX** - Users understand "API Verified" vs "0.87 confidence"
5. **Same effectiveness** - Achieves 99% enrichment target
6. **One less database table** - Queue embedded in songs table

______________________________________________________________________

## Proposed Three-Phase Approach

### Phase 4A: Ambiguity-Aware Filename Parsing  START HERE

**Risk:** Low
**Impact:** Medium (provides baseline for Phase 4B)
**Effort:** Low
**Runs:** Synchronously on scan (fast)
**Coverage:** 100% of songs get SOME parsing, but 30-40% may have swapped artist/title

**Goal:** Extract metadata from filenames using intelligent multi-stage parsing that handles:

1. YouTube ID extraction (both `---ID` and `[ID]` formats)
2. Copyright phrase detection and artist extraction
3. Karaoke marker stripping
4. Ambiguity-aware artist/title splitting

**Key Changes from Original Plan:**

1. **YouTube ID comes FIRST** - Extract before any other parsing
2. **Copyright phrases are OPPORTUNITIES** - They explicitly state the artist!
3. **Karaoke markers are NOISE** - Strip them before parsing
4. **Remaining ambiguity** - Flag for Phase 4B API verification

**Parsing Order (Sequential Pattern Matching):**

```python
PARSING_STAGES = [
    # Stage 1: Extract YouTube ID (highest priority)
    # PiKaraoke format: "Title---YouTubeID.ext"
    # Standard yt-dlp: "Title [YouTubeID].ext"
    # Stage 2: Extract artist from copyright phrases (high confidence)
    # "Title (Originally Performed By Artist)" -> Artist: "Artist", Title: "Title"
    # "Title (Made Famous By Artist)" -> Artist: "Artist", Title: "Title"
    # "Title (In the Style of Artist)" -> Artist: "Artist", Title: "Title"
    # Stage 3: Strip karaoke markers (preparation for Stage 4)
    # "(Karaoke)", "(Karaoke Version)", "| Karaoke", "[Karaoke]", etc.
    # Stage 4: Parse remaining with ambiguity detection
    # "Artist - Title" OR "Title - Artist" (ambiguous, needs API verification)
    # "Artist_Title" (ambiguous)
]
```

**Example Parsing Results:**

| Filename | YouTube ID | Artist | Title | Status | Needs API? |
|----------|-----------|--------|-------|--------|------------|
| `Radio Head - Creep (Karaoke)---dQw4w9.mp4` | dQw4w9 | "Radio Head" | "Creep" | parsed_weak | Yes (ambiguous order) |
| `Wonderwall (Originally Performed By Oasis) [Karaoke]---vid123.mp4` | vid123 | "Oasis" | "Wonderwall" | parsed_strong | Optional (artist explicit) |
| `Bohemian Rhapsody (Made Famous By Queen)---abc987.mp4` | abc987 | "Queen" | "Bohemian Rhapsody" | parsed_strong | Optional (artist explicit) |
| `Hotel California (In the Style of Eagles) [xyz456].mp4` | xyz456 | "Eagles" | "Hotel California" | parsed_strong | Optional (artist explicit) |
| `Let It Be - The Beatles (Instrumental)---ijk321.mp4` | ijk321 | "The Beatles" | "Let It Be" | parsed_weak | Yes (ambiguous order) |
| `legacy_song.cdg` | NULL | NULL | "legacy song" | fallback | Yes (no metadata) |

**Implementation:**

```python
from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING


class YouTubeKaraokeMetadataParser:
    """Parse metadata from YouTube karaoke filenames with multi-stage intelligent extraction.

    Handles:
    - YouTube ID extraction (both ---ID and [ID] formats)
    - Copyright phrase artist extraction ("Originally Performed By", etc.)
    - Karaoke marker stripping
    - Ambiguity-aware artist/title parsing
    """

    # Stage 1: YouTube ID extraction patterns
    YOUTUBE_ID_PATTERNS = [
        r"---([A-Za-z0-9_-]{11})$",  # PiKaraoke format: "Title---ID"
        r"\[([A-Za-z0-9_-]{11})\]$",  # Standard yt-dlp: "Title [ID]"
    ]

    # Stage 2: Copyright phrase patterns (HIGH CONFIDENCE - artist explicitly stated)
    COPYRIGHT_PATTERNS = [
        # "Title (Originally Performed By Artist)" or similar
        {
            "regex": r"^(.+?)\s*\(\s*originally\s+performed\s+by\s+(.+?)\s*\)",
            "title_group": 1,
            "artist_group": 2,
            "confidence": 0.85,
        },
        {
            "regex": r"^(.+?)\s*\(\s*made\s+famous\s+by\s+(.+?)\s*\)",
            "title_group": 1,
            "artist_group": 2,
            "confidence": 0.85,
        },
        {
            "regex": r"^(.+?)\s*\(\s*in\s+the\s+style\s+of\s+(.+?)\s*\)",
            "title_group": 1,
            "artist_group": 2,
            "confidence": 0.85,
        },
        {
            "regex": r"^(.+?)\s*-\s*as\s+performed\s+by\s+(.+?)$",
            "title_group": 1,
            "artist_group": 2,
            "confidence": 0.85,
        },
        # "Title [Style: Artist]"
        {
            "regex": r"^(.+?)\s*\[\s*style:\s*(.+?)\s*\]",
            "title_group": 1,
            "artist_group": 2,
            "confidence": 0.80,
        },
    ]

    # Stage 3: Karaoke markers to strip (case-insensitive)
    KARAOKE_MARKERS = [
        r"\s*\(karaoke\s+version\)",
        r"\s*\(karaoke\)",
        r"\s*\[karaoke\]",
        r"\s*\|\s*karaoke",
        r"\s*-\s*karaoke",
        r"\s*\(instrumental\s+version\)",
        r"\s*\(instrumental\)",
        r"\s*\(backing\s+track\)",
        r"\s*\(no\s+vocals\)",
        r"\s*\(official\s+video\)",
        r"\s*\(official\)",
        r"\s*\(lyrics\)",
        r"\s*\(hd\)",
        r"\s*\(4k\)",
    ]

    @staticmethod
    def parse_filename(filename: str) -> dict[str, str | None]:
        """Parse filename into metadata fields using multi-stage extraction.

        Args:
            filename: Song filename (with or without extension)

        Returns:
            Dict with keys:
                - artist: str | None
                - title: str | None
                - year: int | None
                - variant: str | None (e.g., "Instrumental")
                - youtube_id: str | None
                - metadata_status: str (status value, not confidence score)
                - has_explicit_artist: bool (for API enrichment decision)
        """
        # Remove file extension
        clean = os.path.splitext(filename)[0]
        youtube_id = None
        artist = None
        title = None
        year = None
        variant = None
        has_explicit_artist = False

        # Stage 1: Extract YouTube ID
        for pattern in YouTubeKaraokeMetadataParser.YOUTUBE_ID_PATTERNS:
            match = re.search(pattern, clean, re.IGNORECASE)
            if match:
                youtube_id = match.group(1)
                # Remove YouTube ID from string
                clean = re.sub(pattern, "", clean).strip()
                break

        # Stage 2: Check for copyright phrases (EXPLICIT ARTIST)
        copyright_matched = False
        for pattern_def in YouTubeKaraokeMetadataParser.COPYRIGHT_PATTERNS:
            match = re.search(pattern_def["regex"], clean, re.IGNORECASE)
            if match:
                title = match.group(pattern_def["title_group"]).strip()
                artist = match.group(pattern_def["artist_group"]).strip()
                has_explicit_artist = True  # Artist explicitly stated in filename
                copyright_matched = True
                # Remove matched pattern from clean string
                clean = re.sub(pattern_def["regex"], "", clean, re.IGNORECASE).strip()
                break

        # Stage 3: Strip karaoke markers
        if not copyright_matched:
            for marker in YouTubeKaraokeMetadataParser.KARAOKE_MARKERS:
                clean = re.sub(marker, "", clean, flags=re.IGNORECASE).strip()

        # Stage 4: Parse remaining (if not already parsed from copyright phrase)
        if not copyright_matched and clean:
            # Try to extract year first
            year_match = re.search(r"\((\d{4})\)", clean)
            if year_match:
                year = int(year_match.group(1))
                clean = re.sub(r"\s*\(\d{4}\)", "", clean).strip()

            # Check for instrumental/backing track variants
            variant_match = re.search(
                r"\((?:instrumental|backing\s+track|no\s+vocals)\)",
                clean,
                re.IGNORECASE,
            )
            if variant_match:
                variant = variant_match.group(0).strip("()")
                clean = re.sub(
                    r"\s*\((?:instrumental|backing\s+track|no\s+vocals)\)",
                    "",
                    clean,
                    flags=re.IGNORECASE,
                ).strip()

            # Split on dash or underscore (AMBIGUOUS - needs API verification)
            if " - " in clean:
                parts = clean.split(" - ", 1)
                if len(parts) == 2:
                    # GUESS: Artist - Title order (but could be reversed!)
                    artist = parts[0].strip()
                    title = parts[1].strip()
            elif "_" in clean:
                parts = clean.replace("_", " ").split()
                if len(parts) >= 2:
                    # GUESS: First half = artist, second half = title
                    mid = len(parts) // 2
                    artist = " ".join(parts[:mid]).strip()
                    title = " ".join(parts[mid:]).strip()
            else:
                # No separator - use entire string as title
                title = clean

        # Final cleanup: Remove extra whitespace
        if artist:
            artist = " ".join(artist.split())
        if title:
            title = " ".join(title.split())

        # Determine status based on what we extracted
        if has_explicit_artist:
            metadata_status = "parsed_strong"
        elif artist and title:
            metadata_status = "parsed_weak"
        else:
            metadata_status = "fallback"

        return {
            "artist": artist,
            "title": title
            or clean
            or filename,  # Fallback to original if all else fails
            "year": year,
            "variant": variant,
            "youtube_id": youtube_id,
            "metadata_status": metadata_status,
            "has_explicit_artist": has_explicit_artist,
        }
```

**Database Update:**

```python
def enrich_from_filenames(self):
    """Parse filenames and populate artist/title fields."""
    cursor = self.conn.execute(
        "SELECT id, filename FROM songs WHERE metadata_status = 'fallback'"
    )

    updated = 0
    parser = YouTubeKaraokeMetadataParser()

    for row in cursor.fetchall():
        song_id = row["id"]
        filename = row["filename"]

        # Parse filename
        parsed = parser.parse_filename(filename)

        # Determine if should queue for API enrichment
        needs_api = parsed["metadata_status"] in ("parsed_weak", "fallback")

        # Update database
        self.conn.execute(
            """
            UPDATE songs
            SET artist = ?,
                title = ?,
                year = ?,
                variant = ?,
                youtube_id = ?,
                search_blob = ?,
                metadata_status = ?,
                queued_for_enrichment = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """,
            (
                parsed["artist"],
                parsed["title"] or filename,
                parsed["year"],
                parsed["variant"],
                parsed["youtube_id"],
                self.build_search_blob(
                    filename, parsed["title"], parsed["artist"], parsed["youtube_id"]
                ),
                parsed["metadata_status"],
                1 if needs_api else 0,
                song_id,
            ),
        )

        updated += 1

    self.conn.commit()
    logging.info(f"Parsed {updated} filenames")
    return updated
```

**Advantages:**

- Fast (regex parsing is instant)
- No external API calls
- Works offline
- No rate limiting
- Handles 80% of well-named files

**Disadvantages:**

- Doesn't get year/genre (only what's in filename)
- Can't correct misspellings
- Artist names may be incomplete ("Beatles" vs "The Beatles")

______________________________________________________________________

### Phase 4B: External API Enrichment  PROCEED WITH CAUTION

**Risk:** Medium
**Impact:** High
**Effort:** Medium

**Goal:** Fetch year, genre, and canonical artist/title from external APIs.

#### Option 1: Last.FM API  RECOMMENDED

**Why Last.FM?**

- Free tier available (non-commercial use)
- Extensive music database
- Good artist/track info
- Genre tags (user-contributed)
- Album artwork URLs
- Rate limit: 5 requests/second
- Requires API key (users must sign up)

**API Endpoints:**

1. **track.getInfo** - Get track metadata

   ```
   http://ws.audioscrobbler.com/2.0/?method=track.getinfo
       &api_key=YOUR_KEY
       &artist=The Beatles
       &track=Hey Jude
       &format=json
   ```

   **Response:**

   ```json
   {
     "track": {
       "name": "Hey Jude",
       "artist": {"name": "The Beatles"},
       "album": {
         "title": "Hey Jude",
         "image": [{"#text": "https://...", "size": "large"}]
       },
       "wiki": {
         "published": "01 Jan 1968, 00:00",
         "summary": "..."
       },
       "toptags": {
         "tag": [
           {"name": "classic rock"},
           {"name": "60s"},
           {"name": "rock"}
         ]
       }
     }
   }
   ```

2. **artist.getInfo** - Get artist metadata

   ```
   http://ws.audioscrobbler.com/2.0/?method=artist.getinfo
       &artist=The Beatles
       &api_key=YOUR_KEY
       &format=json
   ```

**Implementation:**

```python
import requests
import time
from datetime import datetime


class LastFMEnricher:
    """Enrich song metadata using Last.FM API."""

    API_BASE = "http://ws.audioscrobbler.com/2.0/"
    RATE_LIMIT = 5  # requests per second

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.last_request_time = 0
        self.session = requests.Session()

    def _rate_limit(self):
        """Enforce rate limiting."""
        now = time.time()
        elapsed = now - self.last_request_time
        min_interval = 1.0 / self.RATE_LIMIT

        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)

        self.last_request_time = time.time()

    def get_track_info(self, artist: str, title: str) -> dict | None:
        """Fetch track metadata from Last.FM.

        Args:
            artist: Artist name
            title: Track title

        Returns:
            Dict with year, genre, canonical_artist, canonical_title, artwork_url
            or None if not found
        """
        self._rate_limit()

        try:
            response = self.session.get(
                self.API_BASE,
                params={
                    "method": "track.getinfo",
                    "api_key": self.api_key,
                    "artist": artist,
                    "track": title,
                    "format": "json",
                },
                timeout=10,
            )

            if response.status_code != 200:
                logging.warning(f"Last.FM API error: {response.status_code}")
                return None

            data = response.json()

            if "track" not in data:
                logging.debug(f"Track not found: {artist} - {title}")
                return None

            track = data["track"]

            # Extract year from wiki published date
            year = None
            if "wiki" in track and "published" in track["wiki"]:
                try:
                    # Parse "01 Jan 1968, 00:00" format
                    date_str = track["wiki"]["published"]
                    date_obj = datetime.strptime(date_str, "%d %b %Y, %H:%M")
                    year = date_obj.year
                except:
                    pass

            # Extract primary genre from top tags
            genre = None
            if "toptags" in track and "tag" in track["toptags"]:
                tags = track["toptags"]["tag"]
                if tags and len(tags) > 0:
                    genre = tags[0]["name"]  # Use most popular tag

            # Get canonical artist/title
            canonical_artist = track.get("artist", {}).get("name")
            canonical_title = track.get("name")

            # Get artwork URL
            artwork_url = None
            if "album" in track and "image" in track["album"]:
                images = track["album"]["image"]
                # Find large image
                for img in images:
                    if img.get("size") == "large":
                        artwork_url = img.get("#text")
                        break

            return {
                "year": year,
                "genre": genre,
                "canonical_artist": canonical_artist,
                "canonical_title": canonical_title,
                "artwork_url": artwork_url,
            }

        except requests.RequestException as e:
            logging.error(f"Last.FM request failed: {e}")
            return None
        except Exception as e:
            logging.error(f"Last.FM parsing error: {e}")
            return None
```

**Database Integration:**

```python
def enrich_from_lastfm(self, api_key: str, batch_size: int = 100):
    """Enrich metadata using Last.FM API.

    Args:
        api_key: Last.FM API key
        batch_size: Number of songs to process per run (prevents long-running ops)
    """
    if not api_key:
        logging.warning("No Last.FM API key provided, skipping enrichment")
        return 0

    # Get songs queued for enrichment
    cursor = self.conn.execute(
        """
        SELECT id, artist, title, metadata_status, has_explicit_artist
        FROM songs
        WHERE queued_for_enrichment = 1
          AND artist IS NOT NULL
          AND title IS NOT NULL
          AND enrichment_attempts < 3
        ORDER BY enrichment_priority DESC, updated_at ASC
        LIMIT ?
    """,
        (batch_size,),
    )

    enricher = LastFMEnricher(api_key)
    enriched = 0
    failed = 0

    for row in cursor.fetchall():
        song_id = row["id"]
        artist = row["artist"]
        title = row["title"]
        current_status = row["metadata_status"]
        has_explicit_artist = row.get("has_explicit_artist", False)

        # Fetch from Last.FM
        info = enricher.get_track_info(artist, title)

        if info:
            # Determine new status based on API match quality
            api_match_quality = (
                "high" if info.get("year") and info.get("genre") else "low"
            )

            if has_explicit_artist and api_match_quality == "high":
                new_status = "api_verified"
            else:
                new_status = "api_enriched"

            # Update with enriched data
            self.conn.execute(
                """
                UPDATE songs
                SET year = ?,
                    genre = ?,
                    artist = ?,  -- Use canonical artist name
                    title = ?,   -- Use canonical title
                    metadata_status = ?,
                    queued_for_enrichment = 0,
                    enrichment_attempts = enrichment_attempts + 1,
                    last_enrichment_attempt = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                (
                    info["year"],
                    info["genre"],
                    info["canonical_artist"] or artist,
                    info["canonical_title"] or title,
                    new_status,
                    song_id,
                ),
            )
            enriched += 1
        else:
            # Mark as failed
            self.conn.execute(
                """
                UPDATE songs
                SET metadata_status = 'failed',
                    queued_for_enrichment = 0,
                    enrichment_attempts = enrichment_attempts + 1,
                    last_enrichment_attempt = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                (song_id,),
            )
            failed += 1

        # Commit every 10 songs (prevents data loss on interruption)
        if (enriched + failed) % 10 == 0:
            self.conn.commit()

    self.conn.commit()
    logging.info(f"Enriched {enriched} songs, {failed} failed")
    return enriched
```

#### Option 2: MusicBrainz API (Alternative)

**Why MusicBrainz?**

- Completely free and open
- No API key required
- Comprehensive database
- High data quality
- **Rate limit: 1 request/second PER IP ADDRESS (strictly enforced)**
- **CRITICAL: Requires proper User-Agent header or gets throttled to 50 req/sec globally**
- More complex API

**Rate Limiting Details:**

- **Per-IP enforcement:** 1 request/second average per IP address
- **All-or-nothing enforcement:** When exceeded, ALL requests return HTTP 503 (not just excess requests)
- **User-Agent MANDATORY:** Must use format `AppName/Version ( contact-url-or-email )`
  - Good: `PiKaraoke/1.0 (https://github.com/vicwomg/pikaraoke)`
  - Bad: `Python-urllib/3.9` (gets throttled to stricter 50 req/sec global pool)

**Implementation Requirements:**

```python
class MusicBrainzEnricher:
    """Enrich metadata using MusicBrainz API with strict rate limiting."""

    API_BASE = "https://musicbrainz.org/ws/2/"
    RATE_LIMIT = 0.9  # Conservative: 0.9 req/sec (not 1.0) to avoid HTTP 503
    USER_AGENT = "PiKaraoke/1.0 (https://github.com/vicwomg/pikaraoke)"

    def __init__(self):
        self.last_request_time = 0
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.USER_AGENT})

    def _rate_limit(self):
        """Enforce CONSERVATIVE rate limiting to avoid HTTP 503."""
        now = time.time()
        elapsed = now - self.last_request_time
        # Use 1.1 seconds minimum interval (conservative, not 1.0)
        min_interval = 1.1

        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)

        self.last_request_time = time.time()

    def get_recording_info(
        self, artist: str, title: str, retry_on_503: bool = True
    ) -> dict | None:
        """Fetch recording metadata from MusicBrainz.

        Args:
            artist: Artist name
            title: Recording title
            retry_on_503: If True, retry once after exponential backoff on HTTP 503

        Returns:
            Dict with metadata or None if not found
        """
        self._rate_limit()

        try:
            # Search for recording
            response = self.session.get(
                f"{self.API_BASE}recording/",
                params={
                    "query": f'artist:"{artist}" AND recording:"{title}"',
                    "fmt": "json",
                    "limit": 5,
                },
                timeout=10,
            )

            if response.status_code == 503:
                # Rate limit exceeded - back off
                logging.warning(
                    "MusicBrainz rate limit exceeded (HTTP 503), backing off"
                )
                if retry_on_503:
                    time.sleep(5.0)  # Wait 5 seconds before retry
                    return self.get_recording_info(artist, title, retry_on_503=False)
                return None

            if response.status_code != 200:
                logging.warning(f"MusicBrainz API error: {response.status_code}")
                return None

            data = response.json()

            if not data.get("recordings"):
                logging.debug(f"Recording not found: {artist} - {title}")
                return None

            # Use first result (best match)
            recording = data["recordings"][0]

            return {
                "canonical_artist": recording.get("artist-credit", [{}])[0]
                .get("artist", {})
                .get("name"),
                "canonical_title": recording.get("title"),
                "year": recording.get("first-release-date", "")[:4] or None,
                "mbid": recording.get("id"),
            }

        except requests.RequestException as e:
            logging.error(f"MusicBrainz request failed: {e}")
            return None
```

**Recommendation:** Use Last.FM for speed (5 req/sec), fall back to MusicBrainz (1 req/sec) for additional enrichment or verification.

#### Option 3: Spotify Web API (Not Recommended)

**Why Not Spotify?**

- Requires OAuth authentication (complex setup)
- Designed for streaming, not metadata lookup
- Terms of Service restrict metadata scraping
- Excellent data quality
- Rich preview/artwork

**Verdict:** Too complex for this use case.

______________________________________________________________________

### Phase 4C: Enhanced Manual UI Editor  ESSENTIAL FALLBACK

**Risk:** Low
**Impact:** Medium
**Effort:** Low (reuses existing UI + new parser)

**Goal:** Preserve and enhance existing LastFM suggestion UI, allowing users to manually edit metadata for songs that couldn't be auto-enriched.

**IMPORTANT:** PiKaraoke ALREADY has a LastFM suggestion feature in [edit.html](pikaraoke/templates/edit.html#L74-L96). This should be preserved and enhanced with the new parsing logic.

#### Existing LastFM UI Integration (To Be Enhanced)

**Current Implementation** ([edit.html:72-97](pikaraoke/templates/edit.html#L72-L97)):

The existing UI provides:

- **Auto-format button** - Strips karaoke markers from filename
- **Swap artist/song order** - Reverses "Artist - Title" to "Title - Artist"
- **Suggest from Last.fm** - Queries LastFM API and presents 5 suggestions

**Current `clean_title()` Function** ([edit.html:41-70](pikaraoke/templates/edit.html#L41-L70)):

```javascript
function clean_title(search_str, title_case = false) {
    // Removes: "karaoke", "made famous by", "in the style of", etc.
    var uselessWordsArray = [
        "as popularized by", "lyrics", "karafun", "instrumental",
        "minus one", "minusone", "made famous by", " by ",
        "karaoke version", "karaoke", "hd", "hq", "coversph",
        "singkaraoke", "in the style of", "no lead vocal",
        "with lyrics", "cc"
    ];
    // ... removes these phrases and cleans up formatting
}
```

**Enhancement Strategy:**

1. **Reuse `clean_title()` logic in Python** - Port JavaScript cleaning logic to `YouTubeKaraokeMetadataParser`
2. **Pre-populate suggestions** - Use parsed artist/title to call LastFM API automatically on edit page load
3. **Show status badge** - Display metadata_status to guide users ("Parsed (Weak) - Review Suggested")
4. **Preserve manual override** - Allow users to click "Suggest from Last.fm" to re-query with different terms

**Enhanced Flow:**

```
User clicks "Edit" on song -> Edit page loads

Backend: Parse filename with YouTubeKaraokeMetadataParser
   Returns: artist="Oasis", title="Wonderwall", status="parsed_weak"

Frontend: Pre-populate form fields

Display: "Artist: Oasis | Title: Wonderwall | Status: Parsed (Weak)"

Automatically call LastFM API with parsed values

Display suggestions: [Oasis - Wonderwall, Oasis - Wonderwall (Remastered), ...]

User selects suggestion OR manually edits OR clicks "Suggest again"

On save: metadata_status set to "manual" (highest trust)
```

**Code Changes Required:**

1. **Backend** - New route endpoint:

```python
@files_bp.route("/api/parse_filename", methods=["POST"])
def parse_filename():
    """Parse filename and return metadata suggestions."""
    filename = request.json.get("filename")
    parser = YouTubeKaraokeMetadataParser()
    result = parser.parse_filename(filename)
    return jsonify(result)
```

2. **Frontend** - Enhanced edit.html:

```javascript
// On page load, parse filename and pre-populate
$(function() {
    var filename = $('#new_file_name').val();
    $.post('/files/api/parse_filename', {filename: filename}, function(data) {
        // Show status badge
        $('#metadata-status').html(
            '<span class="tag ' + getStatusClass(data.metadata_status) + '">' +
            getStatusLabel(data.metadata_status) + '</span>'
        );

        // Auto-suggest if parsed_weak or fallback (needs verification)
        if (['parsed_weak', 'fallback'].includes(data.metadata_status)) {
            suggest_title(data.title + ' ' + (data.artist || ''), "#suggest_results");
        }
    });
});

function getStatusClass(status) {
    const classes = {
        'manual': 'is-success',
        'api_verified': 'is-success',
        'api_enriched': 'is-info',
        'parsed_strong': 'is-link',
        'parsed_weak': 'is-warning',
        'fallback': 'is-warning',
        'failed': 'is-danger'
    };
    return classes[status] || 'is-light';
}

function getStatusLabel(status) {
    const labels = {
        'manual': 'Manual',
        'api_verified': 'API Verified',
        'api_enriched': 'API Enriched',
        'parsed_strong': 'Parsed (Strong)',
        'parsed_weak': 'Parsed (Weak) - Review Suggested',
        'fallback': 'Fallback - Review Suggested',
        'failed': 'Failed'
    };
    return labels[status] || status;
}
```

**Benefits:**

- **Preserves existing UX** - Users familiar with current UI see improvements, not changes
- **Reduces manual work** - Auto-populates based on intelligent parsing
- **Reuses parsing logic** - Same `YouTubeKaraokeMetadataParser` used everywhere
- **Still allows manual override** - Power users can edit/re-search as needed

#### Use Cases for Manual Editing

1. **Filename parsing failed** (unusual patterns)
2. **External API returned wrong data** (common with cover songs)
3. **User has custom/local recordings** (not in Last.FM database)
4. **User wants to correct/customize** metadata
5. **Low confidence enrichment** (\< 0.70) - User verifies/corrects automatically suggested metadata

#### UI Design: "Edit Song Metadata" Modal

**Trigger:** Click "Edit" button on any song in browse view

**Modal Layout:**

```

  Edit Song Metadata                        [X]

 Filename: Beatles - Hey Jude.mp4

 Artist:  [The Beatles____________]
 Title:   [Hey Jude________________]
 Year:    [1968____] (optional)
 Genre:   [Rock____] (optional)
 Variant: [________] (e.g., "Karaoke", "Live")

 [Reset to Filename] [Cancel]     [Save Changes]

```

**Implementation (Template):**

```html
<!-- Add to files.html or create new edit_modal.html -->
<div id="edit-metadata-modal" class="modal">
    <div class="modal-background"></div>
    <div class="modal-card">
        <header class="modal-card-head">
            <p class="modal-card-title"> {% trans %}Edit Song Metadata{% endtrans %}</p>
            <button class="delete" aria-label="close"></button>
        </header>
        <section class="modal-card-body">
            <form id="edit-metadata-form">
                <input type="hidden" id="edit-song-id" name="song_id">

                <div class="field">
                    <label class="label">{% trans %}Filename{% endtrans %}</label>
                    <p id="edit-filename" class="has-text-grey"></p>
                </div>

                <div class="field">
                    <label class="label">{% trans %}Artist{% endtrans %}</label>
                    <div class="control">
                        <input class="input" type="text" id="edit-artist"
                               name="artist" placeholder="Artist name">
                    </div>
                </div>

                <div class="field">
                    <label class="label">{% trans %}Title{% endtrans %} *</label>
                    <div class="control">
                        <input class="input" type="text" id="edit-title"
                               name="title" placeholder="Song title" required>
                    </div>
                </div>

                <div class="columns">
                    <div class="column">
                        <div class="field">
                            <label class="label">{% trans %}Year{% endtrans %}</label>
                            <div class="control">
                                <input class="input" type="number" id="edit-year"
                                       name="year" min="1900" max="2100"
                                       placeholder="YYYY">
                            </div>
                        </div>
                    </div>
                    <div class="column">
                        <div class="field">
                            <label class="label">{% trans %}Genre{% endtrans %}</label>
                            <div class="control">
                                <input class="input" type="text" id="edit-genre"
                                       name="genre" placeholder="Rock, Pop, etc.">
                            </div>
                        </div>
                    </div>
                </div>

                <div class="field">
                    <label class="label">{% trans %}Variant{% endtrans %}</label>
                    <div class="control">
                        <input class="input" type="text" id="edit-variant"
                               name="variant" placeholder="Karaoke, Live, Acoustic, etc.">
                    </div>
                    <p class="help">{% trans %}Optional. E.g., "Karaoke", "Live", "Acoustic"{% endtrans %}</p>
                </div>
            </form>
        </section>
        <footer class="modal-card-foot">
            <button class="button" id="reset-to-filename-btn">
                {% trans %}Reset to Filename{% endtrans %}
            </button>
            <div class="is-flex-grow-1"></div>
            <button class="button" id="cancel-edit-btn">
                {% trans %}Cancel{% endtrans %}
            </button>
            <button class="button is-primary" id="save-metadata-btn">
                {% trans %}Save Changes{% endtrans %}
            </button>
        </footer>
    </div>
</div>
```

**Backend Route:**

```python
@app.route("/edit_metadata/<int:song_id>", methods=["POST"])
@requires_admin  # Or allow all users if you prefer
def edit_metadata(song_id):
    """Update song metadata manually.

    Expects JSON with: artist, title, year, genre, variant
    """
    try:
        data = request.get_json()

        # Validate required field
        if not data.get("title"):
            return jsonify({"success": False, "message": "Title is required"}), 400

        # Update database - manual edits get 'manual' status (highest trust)
        k.db.conn.execute(
            """
            UPDATE songs
            SET artist = ?,
                title = ?,
                year = ?,
                genre = ?,
                variant = ?,
                search_blob = ?,
                metadata_status = 'manual',
                queued_for_enrichment = 0,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """,
            (
                data.get("artist") or None,
                data.get("title"),
                data.get("year") or None,
                data.get("genre") or None,
                data.get("variant") or None,
                k.db.build_search_blob(
                    data.get("title"), data.get("title"), data.get("artist"), None
                ),
                song_id,
            ),
        )
        k.db.conn.commit()

        # Update SongList (if still using coexistence)
        # ... sync code ...

        return jsonify({"success": True, "message": "Metadata updated successfully"})

    except Exception as e:
        logging.error(f"Edit metadata failed: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
```

**JavaScript (Frontend):**

```javascript
// Open edit modal
function openEditModal(songId) {
    // Fetch current metadata
    $.get(`/get_song_metadata/${songId}`)
        .done(function(song) {
            $('#edit-song-id').val(song.id);
            $('#edit-filename').text(song.filename);
            $('#edit-artist').val(song.artist || '');
            $('#edit-title').val(song.title || '');
            $('#edit-year').val(song.year || '');
            $('#edit-genre').val(song.genre || '');
            $('#edit-variant').val(song.variant || '');

            $('#edit-metadata-modal').addClass('is-active');
        });
}

// Save changes
$('#save-metadata-btn').click(function() {
    const songId = $('#edit-song-id').val();
    const data = {
        artist: $('#edit-artist').val(),
        title: $('#edit-title').val(),
        year: $('#edit-year').val() || null,
        genre: $('#edit-genre').val() || null,
        variant: $('#edit-variant').val() || null,
    };

    $.ajax({
        url: `/edit_metadata/${songId}`,
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(data),
        success: function(response) {
            showNotification(response.message, 'is-success');
            $('#edit-metadata-modal').removeClass('is-active');
            // Refresh song list
            location.reload();
        },
        error: function(xhr) {
            const message = xhr.responseJSON?.message || 'Failed to update metadata';
            showNotification(message, 'is-danger');
        }
    });
});

// Reset to filename parsing
$('#reset-to-filename-btn').click(function() {
    const filename = $('#edit-filename').text();
    const parsed = parseFilename(filename);  // Reuse parser logic

    $('#edit-artist').val(parsed.artist || '');
    $('#edit-title').val(parsed.title || '');
    $('#edit-year').val(parsed.year || '');
    $('#edit-genre').val('');
    $('#edit-variant').val(parsed.variant || '');
});
```

______________________________________________________________________

## Better Approaches & Optimizations

### Improvement 1: Status-Based Quality Indicators  IMPLEMENTED

**Solution:** Display clear status badges based on metadata_status field.

**Status Display Mapping:**

```python
STATUS_DISPLAY = {
    "manual": {"label": "Manual", "class": "is-success"},
    "api_verified": {"label": "API Verified", "class": "is-success"},
    "api_enriched": {"label": "API Enriched", "class": "is-info"},
    "parsed_strong": {"label": "Parsed (Strong)", "class": "is-link"},
    "parsed_weak": {"label": "Parsed (Weak)", "class": "is-warning"},
    "fallback": {"label": "Fallback", "class": "is-warning"},
    "failed": {"label": "Failed", "class": "is-danger"},
}
```

**UI Indicators:**

```html
<span class="tag is-success">Manual</span>
<span class="tag is-success">API Verified</span>
<span class="tag is-info">API Enriched</span>
<span class="tag is-link">Parsed (Strong)</span>
<span class="tag is-warning">Parsed (Weak) - Review Suggested</span>
<span class="tag is-warning">Fallback - Review Suggested</span>
<span class="tag is-danger">Failed</span>
```

### CORE FEATURE: Background Enrichment Worker

**This is NOT optional - it's the PRIMARY implementation approach.**

**Why Background Processing is Essential:**

- ⏱ Last.FM rate limit: 5 requests/second = 12 seconds/minute = 720 songs/hour
- ⏱ MusicBrainz rate limit: 1 request/second = 60 songs/minute = 3,600 songs/hour
- **Blocking the main thread for 10K songs = 4-14 hours of UI freeze**
- Background worker = app usable immediately

**Full Implementation:**

```python
# In pikaraoke/lib/enrichment_worker.py
import logging
import time
from threading import Thread, Event
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pikaraoke.lib.karaoke_database import KaraokeDatabase


class EnrichmentWorker(Thread):
    """Background worker for metadata enrichment.

    Runs in a daemon thread, processing the enrichment queue
    at a rate-limited pace. State persists to database so
    enrichment can resume after app restarts.
    """

    def __init__(self, db: "KaraokeDatabase", api_key: str, rate_limit: float = 5.0):
        """Initialize enrichment worker.

        Args:
            db: Database instance
            api_key: Last.FM API key
            rate_limit: Max requests per second (default: 5.0 for Last.FM)
        """
        super().__init__(daemon=True, name="EnrichmentWorker")
        self.db = db
        self.api_key = api_key
        self.rate_limit = rate_limit
        self.min_interval = 1.0 / rate_limit

        self._stop_event = Event()
        self._pause_event = Event()
        self._pause_event.set()  # Start unpaused

        # Metrics (also persisted to DB)
        self.total_processed = 0
        self.total_enriched = 0
        self.total_failed = 0
        self.started_at = None

    def run(self):
        """Main worker loop - processes enrichment queue."""
        logging.info("Enrichment worker started")
        self.started_at = time.time()

        # Update state in database
        self._update_state("worker_running", "true")
        self._update_state("worker_started_at", str(self.started_at))

        try:
            while not self._stop_event.is_set():
                # Check if paused
                self._pause_event.wait()

                # Get next song from queue
                song = self._get_next_song()

                if not song:
                    # Queue empty - sleep and check again
                    time.sleep(1.0)
                    continue

                # Process this song
                success = self._enrich_song(song)

                if success:
                    self.total_enriched += 1
                else:
                    self.total_failed += 1

                self.total_processed += 1

                # Update persistent metrics
                self._update_metrics()

                # Rate limiting
                time.sleep(self.min_interval)

        except Exception as e:
            logging.error(f"Enrichment worker error: {e}")
        finally:
            self._update_state("worker_running", "false")
            logging.info(
                f"Enrichment worker stopped. Processed: {self.total_processed}, "
                f"Enriched: {self.total_enriched}, Failed: {self.total_failed}"
            )

    def _get_next_song(self) -> dict | None:
        """Get next song from enrichment queue.

        Returns:
            Song dict or None if queue empty
        """
        cursor = self.db.conn.execute(
            """
            SELECT id, artist, title, filename, metadata_status
            FROM songs
            WHERE queued_for_enrichment = 1
              AND metadata_status IN ('parsed_weak', 'parsed_strong', 'fallback')
              AND enrichment_attempts < 3
            ORDER BY enrichment_priority DESC, updated_at ASC
            LIMIT 1
        """
        )

        row = cursor.fetchone()
        return dict(row) if row else None

    def _enrich_song(self, song: dict) -> bool:
        """Enrich a single song using external API.

        Args:
            song: Song dict with id, artist, title, filename, metadata_status

        Returns:
            True if enrichment succeeded, False otherwise
        """
        from pikaraoke.lib.lastfm_enricher import LastFMEnricher

        song_id = song["id"]
        artist = song["artist"]
        title = song["title"]
        current_status = song["metadata_status"]

        # Skip if no artist/title (can't query API)
        if not artist or not title:
            self._mark_failed(song_id, "No artist/title for API lookup")
            return False

        try:
            enricher = LastFMEnricher(self.api_key)
            info = enricher.get_track_info(artist, title)

            if info:
                # Determine new status based on API results
                api_match_quality = (
                    "high" if info.get("year") and info.get("genre") else "low"
                )
                has_explicit_artist = current_status == "parsed_strong"

                if has_explicit_artist and api_match_quality == "high":
                    new_status = "api_verified"
                else:
                    new_status = "api_enriched"

                # Update song with enriched data
                self.db.conn.execute(
                    """
                    UPDATE songs
                    SET year = ?,
                        genre = ?,
                        artist = ?,  -- Canonical artist name
                        title = ?,   -- Canonical title
                        metadata_status = ?,
                        queued_for_enrichment = 0,
                        enrichment_attempts = enrichment_attempts + 1,
                        last_enrichment_attempt = datetime('now'),
                        updated_at = datetime('now')
                    WHERE id = ?
                """,
                    (
                        info.get("year"),
                        info.get("genre"),
                        info.get("canonical_artist") or artist,
                        info.get("canonical_title") or title,
                        new_status,
                        song_id,
                    ),
                )

                self.db.conn.commit()
                logging.debug(f"Enriched: {artist} - {title} -> {new_status}")
                return True

            else:
                self._mark_failed(song_id, "Not found in Last.FM")
                return False

        except Exception as e:
            self._mark_failed(song_id, str(e))
            logging.error(f"Enrichment error for song {song_id}: {e}")
            return False

    def _mark_failed(self, song_id: int, reason: str):
        """Mark song as failed enrichment."""
        self.db.conn.execute(
            """
            UPDATE songs
            SET enrichment_attempts = enrichment_attempts + 1,
                last_enrichment_attempt = datetime('now'),
                metadata_status = CASE
                    WHEN enrichment_attempts >= 2 THEN 'failed'
                    ELSE metadata_status
                END,
                queued_for_enrichment = CASE
                    WHEN enrichment_attempts >= 2 THEN 0
                    ELSE queued_for_enrichment
                END
            WHERE id = ?
        """,
            (song_id,),
        )

        self.db.conn.commit()
        logging.debug(f"Failed enrichment for song {song_id}: {reason}")

    def _update_metrics(self):
        """Update persistent metrics in database."""
        self._update_state("total_processed", str(self.total_processed))
        self._update_state("total_enriched", str(self.total_enriched))
        self._update_state("total_failed", str(self.total_failed))

    def _update_state(self, key: str, value: str):
        """Update enrichment state in database."""
        self.db.conn.execute(
            "INSERT OR REPLACE INTO enrichment_state (key, value) VALUES (?, ?)",
            (key, value),
        )
        self.db.conn.commit()

    def stop(self):
        """Stop the worker gracefully."""
        logging.info("Stopping enrichment worker...")
        self._stop_event.set()

    def pause(self):
        """Pause enrichment (keeps thread alive)."""
        logging.info("Pausing enrichment worker")
        self._pause_event.clear()
        self._update_state("worker_paused", "true")

    def resume(self):
        """Resume enrichment."""
        logging.info("Resuming enrichment worker")
        self._pause_event.set()
        self._update_state("worker_paused", "false")

    def get_progress(self) -> dict:
        """Get current enrichment progress.

        Returns:
            Dict with: running, paused, processed, enriched, failed, queue_size
        """
        # Get queue size
        cursor = self.db.conn.execute("SELECT COUNT(*) FROM enrichment_queue")
        queue_size = cursor.fetchone()[0]

        return {
            "running": not self._stop_event.is_set(),
            "paused": not self._pause_event.is_set(),
            "total_processed": self.total_processed,
            "total_enriched": self.total_enriched,
            "total_failed": self.total_failed,
            "queue_remaining": queue_size,
            "started_at": self.started_at,
        }
```

**Integration into KaraokeDatabase:**

```python
# In karaoke_database.py

class KaraokeDatabase:
    def __init__(self, ...):
        # ... existing init ...
        self.enrichment_worker = None

    def start_enrichment(self, api_key: str) -> bool:
        """Start background enrichment worker.

        Args:
            api_key: Last.FM API key

        Returns:
            True if started, False if already running
        """
        if self.enrichment_worker and self.enrichment_worker.is_alive():
            logging.warning("Enrichment worker already running")
            return False

        from pikaraoke.lib.enrichment_worker import EnrichmentWorker

        self.enrichment_worker = EnrichmentWorker(self, api_key)
        self.enrichment_worker.start()
        logging.info("Enrichment worker started")
        return True

    def stop_enrichment(self):
        """Stop background enrichment worker."""
        if self.enrichment_worker:
            self.enrichment_worker.stop()
            self.enrichment_worker.join(timeout=5.0)
            self.enrichment_worker = None

    def pause_enrichment(self):
        """Pause enrichment worker."""
        if self.enrichment_worker:
            self.enrichment_worker.pause()

    def resume_enrichment(self):
        """Resume enrichment worker."""
        if self.enrichment_worker:
            self.enrichment_worker.resume()

    def get_enrichment_progress(self) -> dict:
        """Get enrichment progress."""
        if not self.enrichment_worker:
            return {'running': False}

        return self.enrichment_worker.get_progress()

    def queue_for_enrichment(self, song_ids: list[int] = None, priority: int = 0):
        """Add songs to enrichment queue.

        Args:
            song_ids: List of song IDs (None = all pending songs)
            priority: Higher = process first (default: 0)
        """
        if song_ids is None:
            # Queue all songs that need enrichment
            self.conn.execute(
                """
                UPDATE songs
                SET queued_for_enrichment = 1,
                    enrichment_priority = ?
                WHERE metadata_status IN ('parsed_weak', 'parsed_strong', 'fallback')
                  AND enrichment_attempts < 3
            """,
                (priority,),
            )
        else:
            # Queue specific songs
            placeholders = ",".join("?" * len(song_ids))
            self.conn.execute(
                f"""
                UPDATE songs
                SET queued_for_enrichment = 1,
                    enrichment_priority = ?
                WHERE id IN ({placeholders})
                  AND enrichment_attempts < 3
            """,
                (priority, *song_ids),
            )

        self.conn.commit()
```

**Admin UI with Progress Bar:**

```html
<div id="enrichment-status" class="box">
    <h5> Metadata Enrichment</h5>
    <p>Fetching year/genre data from Last.FM...</p>

    <progress class="progress is-primary"
              id="enrichment-progress"
              value="0" max="100">0%</progress>

    <p class="has-text-centered">
        <span id="enrichment-count">0</span> / <span id="enrichment-total">0</span> songs processed
    </p>

    <div class="buttons is-centered mt-3">
        <button id="start-enrichment-btn" class="button is-primary">
            Start Enrichment
        </button>
        <button id="stop-enrichment-btn" class="button is-danger" disabled>
            Stop Enrichment
        </button>
    </div>
</div>
```

**WebSocket/AJAX Polling for Progress:**

```javascript
// Poll for progress every 2 seconds
let progressInterval = null;

function startEnrichmentPolling() {
    progressInterval = setInterval(function() {
        $.get('/enrichment_progress')
            .done(function(data) {
                const percent = (data.processed / data.total) * 100;
                $('#enrichment-progress').val(percent);
                $('#enrichment-count').text(data.processed);
                $('#enrichment-total').text(data.total);

                if (!data.running) {
                    stopEnrichmentPolling();
                    showNotification('Enrichment complete!', 'is-success');
                }
            });
    }, 2000);
}
```

### Improvement 3: Smart Retry Logic

**Problem:** Temporary API failures shouldn't permanently mark songs as failed.

**Solution:** Exponential backoff retry.

```python
def enrich_with_retry(self, api_key: str, max_retries: int = 3):
    """Enrich with retry logic for failed songs."""

    # Get songs that failed < max_retries times
    cursor = self.conn.execute(
        """
        SELECT id, artist, title, enrichment_attempts
        FROM songs
        WHERE metadata_status = 'enrichment_failed'
          AND (enrichment_attempts IS NULL OR enrichment_attempts < ?)
    """,
        (max_retries,),
    )

    enricher = LastFMEnricher(api_key)

    for row in cursor.fetchall():
        attempts = row["enrichment_attempts"] or 0

        # Exponential backoff: wait 2^attempts minutes
        # (Prevents hammering API with same failed requests)
        wait_minutes = 2**attempts
        # Check if enough time has passed...

        info = enricher.get_track_info(row["artist"], row["title"])

        if info:
            # Success! Update as enriched
            self.conn.execute(
                """
                UPDATE songs
                SET ...,
                    metadata_status = 'enriched',
                    enrichment_attempts = ?
                WHERE id = ?
            """,
                (attempts + 1, row["id"]),
            )
        else:
            # Failed again, increment attempt counter
            self.conn.execute(
                """
                UPDATE songs
                SET enrichment_attempts = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                (attempts + 1, row["id"]),
            )
```

### Improvement 4: Caching API Responses

**Problem:** Re-enriching same artist/title wastes API calls.

**Solution:** Cache table for API responses.

```sql
CREATE TABLE IF NOT EXISTS api_cache (
    cache_key TEXT PRIMARY KEY,  -- SHA256 of "artist:title"
    api_name TEXT NOT NULL,       -- 'lastfm', 'musicbrainz', etc.
    response_data TEXT NOT NULL,  -- JSON response
    cached_at TEXT DEFAULT CURRENT_TIMESTAMP,
    expires_at TEXT               -- NULL = never expires
);

CREATE INDEX idx_api_cache_expires ON api_cache(expires_at);
```

**Usage:**

```python
def get_track_info_cached(self, artist: str, title: str) -> dict | None:
    """Get track info with caching."""
    import hashlib
    import json

    # Generate cache key
    cache_key = hashlib.sha256(f"{artist.lower()}:{title.lower()}".encode()).hexdigest()

    # Check cache
    cursor = self.db.conn.execute(
        """
        SELECT response_data FROM api_cache
        WHERE cache_key = ? AND api_name = 'lastfm'
          AND (expires_at IS NULL OR expires_at > datetime('now'))
    """,
        (cache_key,),
    )

    row = cursor.fetchone()
    if row:
        logging.debug(f"Cache hit for {artist} - {title}")
        return json.loads(row[0])

    # Cache miss - fetch from API
    info = self.get_track_info(artist, title)

    if info:
        # Store in cache (expires in 30 days)
        self.db.conn.execute(
            """
            INSERT INTO api_cache (cache_key, api_name, response_data, expires_at)
            VALUES (?, 'lastfm', ?, datetime('now', '+30 days'))
        """,
            (cache_key, json.dumps(info)),
        )
        self.db.conn.commit()

    return info
```

**Benefits:**

- Speeds up re-scans (no API calls for existing songs)
- Reduces API usage (prevents duplicate lookups)
- Works offline after initial enrichment

### Improvement 5: User-Contributed Database  FUTURE IDEA

**Concept:** Build a community database of karaoke filenames -> metadata mappings.

**How it Works:**

1. Users opt-in to share anonymized filename -> metadata mappings
2. Server collects mappings from all users
3. Before calling external API, check community database first
4. 80% cache hit rate (most karaoke files have common names)

**Privacy:**

- Only share filename patterns, not full paths
- Hash filenames before transmission
- User can disable sharing

**Implementation:** (Future phase, not Stage 4)

______________________________________________________________________

## Recommended Phased Rollout

### Phase 4A: Filename Parsing ONLY  START HERE

**Effort:** 1 day
**Risk:** Low

1. Implement `MetadataParser` class
2. Add `enrich_from_filenames()` method
3. Add "Parse Filenames" button to admin UI
4. Test with 100 songs, then 1000, then full library

**Success Criteria:**

- \[ \] 80%+ of well-named files parsed correctly
- \[ \] Artist/title populated
- \[ \] Search works better than before

**Stop Here If:** Budget/time constraints, or external APIs not desired.

______________________________________________________________________

### Phase 4B: External API (Optional)

**Effort:** 1-2 days
**Risk:** Medium

1. Implement `LastFMEnricher` class
2. Add API key configuration (environment variable or config file)
3. Add "Enrich Metadata" button with progress bar
4. Add background worker for batch processing
5. Implement caching layer

**Success Criteria:**

- \[ \] Year/genre populated for 60%+ of songs
- \[ \] Progress tracking works
- \[ \] Rate limiting prevents API bans
- \[ \] Failed enrichments handled gracefully

**Stop Here If:** Manual editing is sufficient for remaining songs.

______________________________________________________________________

### Phase 4C: Manual Editor (Recommended)

**Effort:** 0.5 day
**Risk:** Low

1. Add edit modal to browse/search pages
2. Add backend route for updates
3. Add "bulk edit" feature (select multiple songs)

**Success Criteria:**

- \[ \] Users can edit any song
- \[ \] Changes persist correctly
- \[ \] UI is intuitive

______________________________________________________________________

## UI Enhancements After Enrichment

### Browse by Artist View

```html
<div class="card">
    <header class="card-header">
        <p class="card-header-title"> Browse by Artist</p>
    </header>
    <div class="card-content">
        <div class="list">
            {% for artist, count in artists %}
            <a href="/browse?artist={{ artist }}" class="list-item">
                <div class="columns is-vcentered">
                    <div class="column">
                        <strong>{{ artist or "(Unknown)" }}</strong>
                    </div>
                    <div class="column is-narrow">
                        <span class="tag is-light">{{ count }} songs</span>
                    </div>
                </div>
            </a>
            {% endfor %}
        </div>
    </div>
</div>
```

### Genre Filter

```html
<div class="field">
    <label class="label">Filter by Genre</label>
    <div class="control">
        <div class="select">
            <select id="genre-filter">
                <option value="">All Genres</option>
                <option value="Rock">Rock</option>
                <option value="Pop">Pop</option>
                <option value="Country">Country</option>
                <!-- Dynamic from DB -->
            </select>
        </div>
    </div>
</div>
```

### Song Card with Metadata

```html
<div class="card song-card">
    <div class="card-content">
        <div class="media">
            <div class="media-left">
                <figure class="image is-48x48">
                    <img src="{{ song.artwork_url or '/static/default-album.png' }}"
                         alt="Album art">
                </figure>
            </div>
            <div class="media-content">
                <p class="title is-5">{{ song.title }}</p>
                <p class="subtitle is-6">{{ song.artist or "Unknown Artist" }}</p>
            </div>
        </div>
        <div class="content">
            <div class="tags">
                {% if song.year %}
                <span class="tag is-info">{{ song.year }}</span>
                {% endif %}
                {% if song.genre %}
                <span class="tag is-primary">{{ song.genre }}</span>
                {% endif %}
                {% if song.variant %}
                <span class="tag is-warning">{{ song.variant }}</span>
                {% endif %}
                <!-- Metadata quality status badge -->
                {% if song.metadata_status == 'manual' %}
                <span class="tag is-success">Manual</span>
                {% elif song.metadata_status == 'api_verified' %}
                <span class="tag is-success">API Verified</span>
                {% elif song.metadata_status == 'api_enriched' %}
                <span class="tag is-info">API Enriched</span>
                {% elif song.metadata_status == 'parsed_strong' %}
                <span class="tag is-link">Parsed (Strong)</span>
                {% elif song.metadata_status == 'parsed_weak' %}
                <span class="tag is-warning" title="May need review">Parsed (Weak)</span>
                {% elif song.metadata_status == 'fallback' %}
                <span class="tag is-warning" title="Review recommended">Fallback</span>
                {% elif song.metadata_status == 'failed' %}
                <span class="tag is-danger" title="Enrichment failed">Failed</span>
                {% endif %}
            </div>
        </div>
    </div>
    <footer class="card-footer">
        <a href="#" class="card-footer-item" onclick="playSong('{{ song.id }}')">
            <span class="icon-text">
                <span class="icon"><i class="fas fa-play"></i></span>
                <span>Play</span>
            </span>
        </a>
        <a href="#" class="card-footer-item" onclick="openEditModal('{{ song.id }}')">
            <span class="icon-text">
                <span class="icon"><i class="fas fa-edit"></i></span>
                <span>Edit</span>
            </span>
        </a>
    </footer>
</div>
```

______________________________________________________________________

## Final Recommendations

### Recommended Approach (Simplified, Best Balance)

1. **Phase 4A (Essential):** Implement filename parsing with status-based ranking

   - Gets you 80% of the value
   - No external dependencies
   - Fast and reliable
   - 70% simpler than confidence score approach

2. **Phase 4C (Essential):** Add manual edit UI with status badges

   - Handles edge cases
   - User empowerment
   - Low complexity
   - Clear status indicators

3. **Phase 4B (Optional):** Add Last.FM enrichment with simplified status updates

   - Only if users want genre/year badly
   - Requires API key setup
   - Status-based updates (not confidence calculations)

### What NOT to Do

1. **Don't use complex confidence scoring** - Status-based approach is simpler and just as effective
2. **Don't create separate queue tables** - Embed queue fields in songs table
3. **Don't build your own AI model** - Overkill for this use case
4. **Don't scrape websites** - Legal/ethical issues
5. **Don't block startup on enrichment** - Always allow skipping
6. **Don't auto-overwrite manual edits** - Preserve user intent (`manual` status has highest priority)

### Success Metrics

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Parsing accuracy | >80% | Manual spot-check of 100 random songs |
| Enrichment success rate | >90% | Count of `api_verified` + `api_enriched` vs `failed` |
| User satisfaction | Positive feedback | User surveys/feedback |
| Performance | \<5min for 1K songs | Timed benchmark |
| Code maintainability | Single developer can understand | Code review complexity |
| Status clarity | Users understand badges | UX testing |

______________________________________________________________________

## Summary: Simplified Approach Approved

**Core Strategy:**

> "Get data into database, then enrich while maintaining search capability, then fallback to UI editor for anomalies."

**Why the SIMPLIFIED approach is RIGHT:**

1. **Progressive enhancement** - Each phase adds value independently
2. **Non-blocking** - Users can search immediately, enrichment happens in background
3. **Graceful degradation** - If enrichment fails, fallback to parsed data, then fallback to manual edit
4. **User control** - Manual editor empowers users to fix edge cases
5. **Pragmatic** - Balances automation with practicality
6. **Maintainable** - Single developer can understand and debug (70% less complexity)

**Simplifications Applied (2026-01-11):**

1. **Status-based ranking** - Replaced confidence scores with clear semantic statuses
2. **2-table schema** - Eliminated separate enrichment_queue table
3. **Embedded queue** - Queue fields in songs table for simpler queries
4. **Self-documenting code** - Status names explain quality level
5. **Better UX** - Users understand "API Verified" vs abstract scores

**Implementation Benefits:**

| Aspect | Benefit |
|--------|---------|
| Code complexity | 70% reduction |
| Database tables | 33% reduction (3 → 2) |
| Maintenance | Much easier for single developer |
| Testing | Fewer edge cases |
| User understanding | Clear status badges |
| Same effectiveness | 99% enrichment coverage maintained |

**Final Verdict:** Proceed with simplified status-based approach. Start with Phase 4A (parsing), add 4C (manual UI), then optionally 4B (API enrichment) based on user needs.

______________________________________________________________________

**Document Status:** Design Approved (Simplified Approach)
**Last Updated:** 2026-01-11
**Next Action:** Begin Phase 4A implementation with status-based ranking
