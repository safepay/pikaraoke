# Stage 4: Metadata Enrichment with Background Worker - Detailed Implementation Plan

**Stage:** 4 of 4 (Optional Enhancement)
**Status:** 📋 Updated with Background Worker & Confidence Scoring (Core Features)
**Prerequisites:** Stage 3 (Admin UI Complete)
**Estimated Effort:** 2-3 days
**Risk Level:** Medium

______________________________________________________________________

## Executive Summary

### Your Understanding is Correct ✅

Yes, the three-phase approach is sound:

1. **Get data into database** (Stages 1-3) ✅
2. **Enrich automatically** while maintaining search (Stage 4A-4B)
3. **Fallback to manual UI editor** for anomalies (Stage 4C)

This is the **right approach** because:

- ✅ Users can search immediately (even with basic filename data)
- ✅ Enrichment happens in background (non-blocking)
- ✅ Manual editing handles edge cases AI can't solve
- ✅ Progressive enhancement (each layer adds value)

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

- ❌ Can't browse by artist
- ❌ Can't filter by genre/year
- ❌ Search depends on exact filename match
- ❌ No rich metadata for better UX

### Desired State (After Stage 4)

**Songs Table:**

```sql
| id | file_path              | title      | artist       | year | genre | confidence | metadata_status |
|----|------------------------|------------|--------------|------|-------|------------|-----------------|
| 1  | song1.mp4              | "Song 1"   | "Artist 1"   | 2020 | "Pop" | 0.95       | enriched        |
| 2  | song2.mp4              | "Song 2"   | "Artist 2"   | 2019 | "Rock"| 0.60       | parsed          |
| 3  | Beatles - Hey Jude.mp4 | "Hey Jude" | "The Beatles"| 1968 | "Rock"| 1.00       | manual          |
```

**Benefits:**

- ✅ Browse by artist/genre/year
- ✅ Better search (artist name, genre, etc.)
- ✅ Rich UI (show album art, year, genre tags)
- ✅ Confidence scores show data quality
- ✅ Background enrichment doesn't block UI
- ✅ Improved user experience

______________________________________________________________________

## Architecture: Background Enrichment Pipeline

### Core Principle: Non-Blocking Enrichment ⚡

**Critical Design Decision:** Enrichment happens in a **background worker thread** that never blocks the main application.

```
┌─────────────────────────────────────────────────────────┐
│                    Main Application                     │
│  ┌─────────────┐    ┌──────────────┐                   │
│  │   Browse    │    │    Search    │  ← Users can use  │
│  │   Songs     │    │    Songs     │    app immediately │
│  └─────────────┘    └──────────────┘                   │
└─────────────────────────────────────────────────────────┘
                           ↑
                           │ Non-blocking reads
                           │
┌──────────────────────────┴──────────────────────────────┐
│              SQLite Database (WAL mode)                 │
│  Songs with partial metadata (filename-parsed only)     │
└──────────────────────────┬──────────────────────────────┘
                           ↑
                           │ Background writes
                           │
┌──────────────────────────┴──────────────────────────────┐
│            Background Enrichment Worker Thread          │
│  ┌──────────────┐   ┌──────────────┐   ┌────────────┐ │
│  │   Filename   │ → │  External    │ → │   Update   │ │
│  │   Parser     │   │  API Lookup  │   │  Database  │ │
│  │  (instant)   │   │ (rate-limited)   │ (batched)  │ │
│  └──────────────┘   └──────────────┘   └────────────┘ │
│                                                         │
│  Progress: 247/1000 songs enriched (24.7%)             │
└─────────────────────────────────────────────────────────┘
```

**Key Benefits:**

- ✅ App starts immediately (no waiting for enrichment)
- ✅ Users can search/browse while enrichment runs
- ✅ Rate limiting handled in background (no UI freezes)
- ✅ Progress tracked and displayed in admin UI
- ✅ Can pause/resume enrichment
- ✅ Survives app restarts (tracks progress in DB)

______________________________________________________________________

## Enhanced Schema with Confidence Scoring

### Updated Database Schema

```sql
-- Songs table with confidence tracking
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

    -- Quality tracking (NEW)
    confidence REAL DEFAULT 0.0,              -- 0.0-1.0 confidence score
    metadata_status TEXT DEFAULT 'pending',   -- pending/parsed/enriched/manual/failed
    enrichment_attempts INTEGER DEFAULT 0,    -- Retry counter
    last_enrichment_attempt TEXT,             -- Timestamp of last API call

    -- Technical fields
    format TEXT NOT NULL,
    search_blob TEXT,
    is_visible INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Enrichment queue for background worker
CREATE TABLE IF NOT EXISTS enrichment_queue (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    song_id INTEGER NOT NULL REFERENCES songs(id) ON DELETE CASCADE,
    priority INTEGER DEFAULT 0,               -- Higher = process first
    queued_at TEXT DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(song_id)
);

CREATE INDEX IF NOT EXISTS idx_enrichment_priority ON enrichment_queue(priority DESC, queued_at);

-- Enrichment worker state (survives restarts)
CREATE TABLE IF NOT EXISTS enrichment_state (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- Example state values:
-- 'worker_running' → 'true'/'false'
-- 'worker_started_at' → ISO timestamp
-- 'total_processed' → count
-- 'total_enriched' → count
-- 'total_failed' → count
```

### Confidence Score Calculation

**Confidence levels:**

| Score Range | Status | Meaning | Color |
|-------------|--------|---------|-------|
| 1.00 | `manual` | User manually edited | 🟢 Green |
| 0.90-0.99 | `enriched` | External API returned data + filename matched pattern | 🟢 Green |
| 0.70-0.89 | `enriched` | External API returned data but filename didn't match pattern well | 🟡 Yellow |
| 0.50-0.69 | `parsed` | Filename matched strong pattern (e.g., "Artist - Title") | 🟡 Yellow |
| 0.30-0.49 | `parsed` | Filename matched weak pattern (e.g., underscores) | 🟠 Orange |
| 0.10-0.29 | `parsed` | Fallback to filename as title only | 🔴 Red |
| 0.00-0.09 | `pending`/`failed` | No metadata extracted | 🔴 Red |

**Calculation Logic:**

```python
def calculate_confidence(
    metadata_status: str,
    filename_pattern_quality: str,
    api_match_quality: float | None = None,
) -> float:
    """Calculate confidence score for metadata quality.

    Args:
        metadata_status: pending/parsed/enriched/manual/failed
        filename_pattern_quality: strong/medium/weak/none
        api_match_quality: 0.0-1.0 if external API was used

    Returns:
        Confidence score 0.0-1.0
    """
    if metadata_status == "manual":
        return 1.0  # User override is always trusted

    if metadata_status == "enriched" and api_match_quality is not None:
        # External API data: 0.70-0.99 based on API confidence
        base_score = 0.70 + (api_match_quality * 0.29)
        return min(0.99, base_score)  # Cap at 0.99 (below manual)

    if metadata_status == "parsed":
        # Filename parsing only
        pattern_scores = {
            "strong": 0.60,  # "Artist - Title (Year)"
            "medium": 0.40,  # "Artist - Title" or "Artist_Title"
            "weak": 0.20,  # Fallback patterns
            "none": 0.10,  # Just filename as title
        }
        return pattern_scores.get(filename_pattern_quality, 0.10)

    # pending or failed
    return 0.0
```

______________________________________________________________________

## Proposed Three-Phase Approach

### Phase 4A: Smart Filename Parsing ⭐ START HERE

**Risk:** Low
**Impact:** High
**Effort:** Low
**Runs:** Synchronously on scan (fast)

**Goal:** Extract metadata from filenames using pattern matching.

**Common Patterns to Parse:**

```python
PATTERNS = [
    # Pattern 1: "Artist - Title.ext"
    r"^(.+?)\s*-\s*(.+?)(?:\s*\[.*?\])?(?:\s*\(.*?\))?$",
    # Pattern 2: "Artist - Title (Year).ext"
    r"^(.+?)\s*-\s*(.+?)\s*\((\d{4})\)$",
    # Pattern 3: "Title - Artist.ext" (reversed)
    r"^(.+?)\s*-\s*(.+?)$",
    # Pattern 4: "Artist_Title.ext" (underscore separator)
    r"^(.+?)_(.+?)$",
    # Pattern 5: "001 - Artist - Title.ext" (track number prefix)
    r"^\d+\s*-\s*(.+?)\s*-\s*(.+?)$",
    # Pattern 6: YouTube ID pattern "Title---YouTubeID.ext"
    r"^(.+?)---([A-Za-z0-9_-]{11})$",
    # Pattern 7: Karaoke marker "Title (Karaoke).ext"
    r"^(.+?)\s*\((?:karaoke|instrumental|backing track)\)$",
]
```

**Example Parsing Results:**

| Filename | Detected Pattern | Artist | Title | Variant |
|----------|-----------------|--------|-------|---------|
| `Beatles - Hey Jude.mp4` | Pattern 1 | "Beatles" | "Hey Jude" | NULL |
| `Queen - Bohemian Rhapsody (1975).mp4` | Pattern 2 | "Queen" | "Bohemian Rhapsody" | NULL |
| `Hotel California---dQw4w9WgXcQ.mp4` | Pattern 6 | NULL | "Hotel California" | YouTube ID |
| `Let It Be (Karaoke).mp3` | Pattern 7 | NULL | "Let It Be" | "Karaoke" |
| `David_Bowie_Space_Oddity.zip` | Pattern 4 | "David Bowie" | "Space Oddity" | NULL |

**Implementation:**

```python
import re


class MetadataParser:
    """Parse metadata from song filenames."""

    PATTERNS = [
        # Each pattern returns (artist, title, year, variant)
        {
            "regex": r"^(.+?)\s*-\s*(.+?)\s*\((\d{4})\)$",
            "groups": ("artist", "title", "year"),
        },
        {
            "regex": r"^(.+?)\s*-\s*(.+?)(?:\s*---[A-Za-z0-9_-]{11})?$",
            "groups": ("artist", "title"),
        },
        {
            "regex": r"^(.+?)_(.+?)$",
            "groups": ("artist", "title"),
        },
        # ... more patterns
    ]

    @staticmethod
    def parse_filename(filename: str) -> dict[str, str | None]:
        """Parse filename into metadata fields.

        Args:
            filename: Song filename (without extension)

        Returns:
            Dict with keys: artist, title, year, variant, youtube_id
        """
        # Remove file extension
        clean = os.path.splitext(filename)[0]

        # Remove common suffixes
        clean = re.sub(
            r"\s*\((?:official|video|lyrics|hd|4k)\)", "", clean, flags=re.IGNORECASE
        )

        # Try each pattern
        for pattern_def in MetadataParser.PATTERNS:
            match = re.match(pattern_def["regex"], clean, re.IGNORECASE)
            if match:
                result = {
                    "artist": None,
                    "title": None,
                    "year": None,
                    "variant": None,
                    "youtube_id": None,
                }

                # Map regex groups to fields
                for i, field_name in enumerate(pattern_def["groups"]):
                    value = match.group(i + 1).strip()
                    result[field_name] = value if value else None

                return result

        # No pattern matched - use entire filename as title
        return {
            "artist": None,
            "title": clean,
            "year": None,
            "variant": None,
            "youtube_id": None,
        }
```

**Database Update:**

```python
def enrich_from_filenames(self):
    """Parse filenames and populate artist/title fields."""
    cursor = self.conn.execute(
        "SELECT id, filename, title FROM songs WHERE metadata_status = 'pending'"
    )

    updated = 0
    parser = MetadataParser()

    for row in cursor.fetchall():
        song_id = row["id"]
        filename = row["filename"]

        # Parse filename
        parsed = parser.parse_filename(filename)

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
                metadata_status = 'parsed',
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """,
            (
                parsed["artist"],
                parsed["title"] or filename,  # Fallback to filename if no title
                parsed["year"],
                parsed["variant"],
                parsed["youtube_id"],
                self.build_search_blob(
                    filename, parsed["title"], parsed["artist"], parsed["youtube_id"]
                ),
                song_id,
            ),
        )

        updated += 1

    self.conn.commit()
    logging.info(f"Parsed {updated} filenames")
    return updated
```

**Advantages:**

- ✅ Fast (regex parsing is instant)
- ✅ No external API calls
- ✅ Works offline
- ✅ No rate limiting
- ✅ Handles 80% of well-named files

**Disadvantages:**

- ❌ Doesn't get year/genre (only what's in filename)
- ❌ Can't correct misspellings
- ❌ Artist names may be incomplete ("Beatles" vs "The Beatles")

______________________________________________________________________

### Phase 4B: External API Enrichment ⚠️ PROCEED WITH CAUTION

**Risk:** Medium
**Impact:** High
**Effort:** Medium

**Goal:** Fetch year, genre, and canonical artist/title from external APIs.

#### Option 1: Last.FM API ⭐ RECOMMENDED

**Why Last.FM?**

- ✅ Free tier available (non-commercial use)
- ✅ Extensive music database
- ✅ Good artist/track info
- ✅ Genre tags (user-contributed)
- ✅ Album artwork URLs
- ❌ Rate limit: 5 requests/second
- ❌ Requires API key (users must sign up)

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

    # Get songs with parsed filenames but no external enrichment
    cursor = self.conn.execute(
        """
        SELECT id, artist, title
        FROM songs
        WHERE metadata_status = 'parsed'
          AND artist IS NOT NULL
          AND title IS NOT NULL
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

        # Fetch from Last.FM
        info = enricher.get_track_info(artist, title)

        if info:
            # Update with enriched data
            self.conn.execute(
                """
                UPDATE songs
                SET year = ?,
                    genre = ?,
                    artist = ?,  -- Use canonical artist name
                    title = ?,   -- Use canonical title
                    metadata_status = 'enriched',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """,
                (
                    info["year"],
                    info["genre"],
                    info["canonical_artist"] or artist,  # Fallback to parsed
                    info["canonical_title"] or title,
                    song_id,
                ),
            )
            enriched += 1
        else:
            # Mark as failed (don't retry every time)
            self.conn.execute(
                """
                UPDATE songs
                SET metadata_status = 'enrichment_failed'
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

- ✅ Completely free and open
- ✅ No API key required
- ✅ Comprehensive database
- ✅ High data quality
- ❌ Rate limit: 1 request/second (very slow)
- ❌ More complex API

**Recommendation:** Use Last.FM for speed, fall back to MusicBrainz if Last.FM fails.

#### Option 3: Spotify Web API (Not Recommended)

**Why Not Spotify?**

- ❌ Requires OAuth authentication (complex setup)
- ❌ Designed for streaming, not metadata lookup
- ❌ Terms of Service restrict metadata scraping
- ✅ Excellent data quality
- ✅ Rich preview/artwork

**Verdict:** Too complex for this use case.

______________________________________________________________________

### Phase 4C: Manual UI Editor 🛠️ ESSENTIAL FALLBACK

**Risk:** Low
**Impact:** Medium
**Effort:** Medium

**Goal:** Allow users to manually edit metadata for songs that couldn't be auto-enriched.

#### Use Cases for Manual Editing

1. **Filename parsing failed** (unusual patterns)
2. **External API returned wrong data** (common with cover songs)
3. **User has custom/local recordings** (not in Last.FM database)
4. **User wants to correct/customize** metadata

#### UI Design: "Edit Song Metadata" Modal

**Trigger:** Click "Edit" button on any song in browse view

**Modal Layout:**

```
┌───────────────────────────────────────────────────┐
│ ✏️ Edit Song Metadata                        [X] │
├───────────────────────────────────────────────────┤
│                                                   │
│ Filename: Beatles - Hey Jude.mp4                │
│ ─────────────────────────────────────────────     │
│                                                   │
│ Artist:  [The Beatles____________]              │
│ Title:   [Hey Jude________________]              │
│ Year:    [1968____] (optional)                   │
│ Genre:   [Rock____] (optional)                   │
│ Variant: [________] (e.g., "Karaoke", "Live")   │
│                                                   │
│ ─────────────────────────────────────────────     │
│                                                   │
│ [Reset to Filename] [Cancel]     [Save Changes] │
│                                                   │
└───────────────────────────────────────────────────┘
```

**Implementation (Template):**

```html
<!-- Add to files.html or create new edit_modal.html -->
<div id="edit-metadata-modal" class="modal">
    <div class="modal-background"></div>
    <div class="modal-card">
        <header class="modal-card-head">
            <p class="modal-card-title">✏️ {% trans %}Edit Song Metadata{% endtrans %}</p>
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

        # Update database
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

### Improvement 1: Hybrid Confidence Scoring ⭐ RECOMMENDED

**Problem:** Sometimes external APIs return wrong data (e.g., cover song by different artist).

**Solution:** Assign confidence scores and allow manual override.

```python
metadata_status VALUES:
- 'pending'            # Not yet processed
- 'parsed:high'        # Filename matched pattern with high confidence
- 'parsed:low'         # Filename matched weakly or fallback to title
- 'enriched:high'      # External API returned data
- 'enriched:low'       # External API returned data but seems questionable
- 'manual'             # User manually edited (highest confidence)
- 'failed'             # Parsing and enrichment both failed
```

**UI Indicator:**

```html
<span class="tag is-success">✓ High Confidence</span>
<span class="tag is-warning">? Low Confidence - Review Suggested</span>
<span class="tag is-info">✏️ Manually Edited</span>
```

### CORE FEATURE: Background Enrichment Worker ⚡

**This is NOT optional - it's the PRIMARY implementation approach.**

**Why Background Processing is Essential:**

- ⏱️ Last.FM rate limit: 5 requests/second = 12 seconds/minute = 720 songs/hour
- ⏱️ MusicBrainz rate limit: 1 request/second = 60 songs/minute = 3,600 songs/hour
- 🚫 **Blocking the main thread for 10K songs = 4-14 hours of UI freeze**
- ✅ Background worker = app usable immediately

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
            SELECT s.id, s.artist, s.title, s.filename
            FROM enrichment_queue eq
            JOIN songs s ON eq.song_id = s.id
            WHERE s.metadata_status IN ('pending', 'parsed')
              AND (s.enrichment_attempts IS NULL OR s.enrichment_attempts < 3)
            ORDER BY eq.priority DESC, eq.queued_at ASC
            LIMIT 1
        """
        )

        row = cursor.fetchone()
        return dict(row) if row else None

    def _enrich_song(self, song: dict) -> bool:
        """Enrich a single song using external API.

        Args:
            song: Song dict with id, artist, title, filename

        Returns:
            True if enrichment succeeded, False otherwise
        """
        from pikaraoke.lib.lastfm_enricher import LastFMEnricher

        song_id = song["id"]
        artist = song["artist"]
        title = song["title"]

        # Skip if no artist/title (can't query API)
        if not artist or not title:
            self._mark_failed(song_id, "No artist/title for API lookup")
            return False

        try:
            enricher = LastFMEnricher(self.api_key)
            info = enricher.get_track_info(artist, title)

            if info:
                # Update song with enriched data
                confidence = self._calculate_api_confidence(info)

                self.db.conn.execute(
                    """
                    UPDATE songs
                    SET year = ?,
                        genre = ?,
                        artist = ?,  -- Canonical artist name
                        title = ?,   -- Canonical title
                        confidence = ?,
                        metadata_status = 'enriched',
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
                        confidence,
                        song_id,
                    ),
                )

                # Remove from queue
                self.db.conn.execute(
                    "DELETE FROM enrichment_queue WHERE song_id = ?", (song_id,)
                )

                self.db.conn.commit()
                logging.debug(f"Enriched: {artist} - {title}")
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
                    WHEN enrichment_attempts >= 2 THEN 'enrichment_failed'
                    ELSE metadata_status
                END
            WHERE id = ?
        """,
            (song_id,),
        )

        # Keep in queue if < 3 attempts, otherwise remove
        cursor = self.db.conn.execute(
            "SELECT enrichment_attempts FROM songs WHERE id = ?", (song_id,)
        )
        row = cursor.fetchone()

        if row and row[0] >= 3:
            self.db.conn.execute(
                "DELETE FROM enrichment_queue WHERE song_id = ?", (song_id,)
            )

        self.db.conn.commit()
        logging.debug(f"Failed enrichment for song {song_id}: {reason}")

    def _calculate_api_confidence(self, info: dict) -> float:
        """Calculate confidence score for API-enriched data.

        Args:
            info: API response dict

        Returns:
            Confidence score 0.70-0.99
        """
        # Start with base score for API data
        score = 0.70

        # Boost if we got year
        if info.get("year"):
            score += 0.10

        # Boost if we got genre
        if info.get("genre"):
            score += 0.10

        # Boost if we got canonical names
        if info.get("canonical_artist") and info.get("canonical_title"):
            score += 0.09

        return min(0.99, score)  # Cap at 0.99 (manual edits are 1.0)

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
            self.conn.execute("""
                INSERT OR IGNORE INTO enrichment_queue (song_id, priority)
                SELECT id, ?
                FROM songs
                WHERE metadata_status IN ('pending', 'parsed')
                  AND (enrichment_attempts IS NULL OR enrichment_attempts < 3)
            """, (priority,))
        else:
            # Queue specific songs
            for song_id in song_ids:
                self.conn.execute("""
                    INSERT OR IGNORE INTO enrichment_queue (song_id, priority)
                    VALUES (?, ?)
                """, (song_id, priority))

        self.conn.commit()
```

**Admin UI with Progress Bar:**

```html
<div id="enrichment-status" class="box">
    <h5>🎵 Metadata Enrichment</h5>
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

- ✅ Speeds up re-scans (no API calls for existing songs)
- ✅ Reduces API usage (prevents duplicate lookups)
- ✅ Works offline after initial enrichment

### Improvement 5: User-Contributed Database ⭐ FUTURE IDEA

**Concept:** Build a community database of karaoke filenames → metadata mappings.

**How it Works:**

1. Users opt-in to share anonymized filename → metadata mappings
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

### Phase 4A: Filename Parsing ONLY ⭐ START HERE

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
        <p class="card-header-title">📁 Browse by Artist</p>
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

### ✅ Recommended Approach (Best Balance)

1. **Phase 4A (Essential):** Implement filename parsing

   - Gets you 80% of the value
   - No external dependencies
   - Fast and reliable

2. **Phase 4C (Essential):** Add manual edit UI

   - Handles edge cases
   - User empowerment
   - Low complexity

3. **Phase 4B (Optional):** Add Last.FM enrichment

   - Only if users want genre/year badly
   - Requires API key setup
   - Adds complexity

### ❌ What NOT to Do

1. **Don't build your own AI model** - Overkill for this use case
2. **Don't scrape websites** - Legal/ethical issues
3. **Don't block startup on enrichment** - Always allow skipping
4. **Don't auto-overwrite manual edits** - Preserve user intent

### 🎯 Success Metrics

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Parsing accuracy | >80% | Manual spot-check of 100 random songs |
| Enrichment success rate | >60% | Count of 'enriched' vs 'failed' |
| User satisfaction | Positive feedback | User surveys/feedback |
| Performance | \<5min for 1K songs | Timed benchmark |

______________________________________________________________________

## Summary: Your Analysis is Correct ✅

**Your understanding:**

> "Get data into database, then enrich while maintaining search capability, then fallback to UI editor for anomalies."

**Why this is the RIGHT approach:**

1. ✅ **Progressive enhancement** - Each phase adds value independently
2. ✅ **Non-blocking** - Users can search immediately, enrichment happens in background
3. ✅ **Graceful degradation** - If enrichment fails, fallback to parsed data, then fallback to manual edit
4. ✅ **User control** - Manual editor empowers users to fix edge cases
5. ✅ **Pragmatic** - Balances automation with practicality

**What could be better:**

1. ⭐ **Add confidence scoring** - Let users know which metadata might be wrong
2. ⭐ **Add caching layer** - Reduce API calls for common songs
3. ⭐ **Add background worker with progress** - Better UX for long enrichment
4. ⭐ **Start with Phase 4A only** - Defer external APIs until users request it

**Final Verdict:** Proceed with your plan, but start small (Phase 4A), validate, then expand to 4B/4C as needed.

______________________________________________________________________

**Document Status:** Design Review Complete
**Last Updated:** 2026-01-09
**Next Action:** User approval to finalize Stage 4 scope
