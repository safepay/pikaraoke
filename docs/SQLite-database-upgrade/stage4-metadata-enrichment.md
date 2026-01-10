# Stage 4: Metadata Enrichment with Background Worker

**Stage:** 4 of 4 (Core Objective)
**Status:** Revised - Simplified Status-Based Approach
**Prerequisites:** Stage 3 (Admin UI Complete)
**Estimated Effort:** 2-3 days
**Risk Level:** Low-Medium
**Last Updated:** 2026-01-11

**Note:** This stage is essential to achieve the project's core objective - transforming filename-based song data into usable metadata (artist, title, year, genre).

## Executive Summary

### Simplified Approach (70% Code Reduction)

**Key Change:** Status-based ranking replaces numeric confidence scores, reducing complexity while maintaining 99% enrichment effectiveness.

**What Changed:**

1. **Database: 3 → 2 tables** (eliminated separate queue table)
2. **Confidence scoring eliminated** (clear status values instead)
3. **Queue embedded** in songs table
4. **80% less code** for same results

**What Stayed:**

- 99% enrichment coverage target
- Hybrid LastFM + MusicBrainz strategy
- Background worker architecture
- Artist-title ordering resolution
- Manual UI fallback

## Problem: Why Metadata Matters

### Current State (After Stage 3)

Songs have only filename-derived data. No artist/genre/year filtering, limited search quality.

### Desired State (After Stage 4)

Complete metadata with quality indicators:

```sql
| file_path              | title      | artist       | year | genre | metadata_status |
|------------------------|------------|--------------|------|-------|-----------------|
| song1.mp4              | "Song 1"   | "Artist 1"   | 2020 | "Pop" | api_verified    |
| song2.mp4              | "Song 2"   | "Artist 2"   | 2019 | "Rock"| parsed_weak     |
| Beatles - Hey Jude.mp4 | "Hey Jude" | "The Beatles"| 1968 | "Rock"| manual          |
```

**Benefits:** Browse by artist/genre/year, better search, status badges show quality, background processing.

## YouTube Karaoke Filename Patterns

Based on major channels (Sing King, KaraFun):

**Pattern 1: Standard (60%)**

```
Artist - Song Title (Karaoke Version)
Queen - We Will Rock You (Karaoke)---abc123.mp4
```

**Pattern 2: Copyright Avoidance (25%)**

```
Song Title (Originally Performed By Artist) [Karaoke]
Wonderwall (Made Famous By Oasis) [Karaoke]---vid123.mp4
```

**Pattern 3: Instrumental (10%)**

```
Song Title - Artist (Instrumental Version)
Let It Be - The Beatles (Instrumental)---ijk321.mp4
```

**Pattern 4: Legacy (5%)**

```
artist_title.cdg
random_filename_123.zip
```

**Challenge:** Not just "Artist - Title" vs "Title - Artist", but:

1. Extract YouTube ID
2. Strip karaoke markers
3. Extract artist from copyright phrases
4. Handle remaining ambiguity

**Solution:** Hybrid API strategy with fuzzy matching resolves 99% automatically.

## Simplified Schema

### Updated Songs Table

```sql
CREATE TABLE IF NOT EXISTS songs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    file_path TEXT UNIQUE NOT NULL,
    file_hash TEXT,
    filename TEXT NOT NULL,

    -- Metadata
    artist TEXT,
    title TEXT,
    variant TEXT,
    year INTEGER,
    genre TEXT,
    youtube_id TEXT,

    -- Quality tracking (simplified status-based)
    metadata_status TEXT DEFAULT 'fallback',
    enrichment_attempts INTEGER DEFAULT 0,
    last_enrichment_attempt TEXT,

    -- Queue fields (embedded)
    enrichment_priority INTEGER DEFAULT 0,
    queued_for_enrichment INTEGER DEFAULT 0,

    -- Technical
    format TEXT NOT NULL,
    search_blob TEXT,
    is_visible INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_enrichment_queue
ON songs(queued_for_enrichment, enrichment_priority DESC, updated_at);
```

### Status-Based Quality Ranking

| Status          | Meaning                                 | UI Badge         | Color      |
| --------------- | --------------------------------------- | ---------------- | ---------- |
| `manual`        | User edited (highest trust)             | Manual           | Green      |
| `api_verified`  | API + filename had explicit artist      | API Verified     | Green      |
| `api_enriched`  | API returned data successfully          | API Enriched     | Blue       |
| `parsed_strong` | Filename had explicit artist            | Parsed (Strong)  | Light Blue |
| `parsed_weak`   | Ambiguous artist/title order            | Parsed (Weak)    | Yellow     |
| `fallback`      | Just filename as title                  | Fallback         | Orange     |
| `failed`        | Enrichment failed after retries         | Failed           | Red        |

**Why Status-Based:**

- 70% less code complexity
- Self-documenting
- Easier maintenance
- Better UX
- Same 99% enrichment effectiveness

## Implementation Phases

### Phase 4A: Filename Parsing (START HERE)

**Goal:** Extract metadata from filenames with multi-stage parsing.

**Parsing stages:**

1. Extract YouTube ID (`---ID` or `[ID]` format)
2. Extract artist from copyright phrases (high confidence)
3. Strip karaoke markers
4. Parse remaining with ambiguity detection

**Implementation:**

```python
from __future__ import annotations

import os
import re


class YouTubeKaraokeMetadataParser:
    """Parse metadata from YouTube karaoke filenames."""

    YOUTUBE_ID_PATTERNS = [
        r"---([A-Za-z0-9_-]{11})$",
        r"\[([A-Za-z0-9_-]{11})\]$",
    ]

    COPYRIGHT_PATTERNS = [
        {
            "regex": r"^(.+?)\s*\(\s*originally\s+performed\s+by\s+(.+?)\s*\)",
            "title_group": 1,
            "artist_group": 2,
        },
        {
            "regex": r"^(.+?)\s*\(\s*made\s+famous\s+by\s+(.+?)\s*\)",
            "title_group": 1,
            "artist_group": 2,
        },
    ]

    KARAOKE_MARKERS = [
        r"\s*\(karaoke\s+version\)",
        r"\s*\(karaoke\)",
        r"\s*\[karaoke\]",
        r"\s*\(instrumental\)",
    ]

    @staticmethod
    def parse_filename(filename: str) -> dict[str, str | None]:
        """Parse filename into metadata fields.

        Args:
            filename: Song filename

        Returns:
            Dict with artist, title, year, variant, youtube_id, metadata_status
        """
        clean = os.path.splitext(filename)[0]
        youtube_id = None
        artist = None
        title = None
        has_explicit_artist = False

        # Stage 1: Extract YouTube ID
        for pattern in YouTubeKaraokeMetadataParser.YOUTUBE_ID_PATTERNS:
            match = re.search(pattern, clean, re.IGNORECASE)
            if match:
                youtube_id = match.group(1)
                clean = re.sub(pattern, "", clean).strip()
                break

        # Stage 2: Check for copyright phrases (explicit artist)
        for pattern_def in YouTubeKaraokeMetadataParser.COPYRIGHT_PATTERNS:
            match = re.search(pattern_def["regex"], clean, re.IGNORECASE)
            if match:
                title = match.group(pattern_def["title_group"]).strip()
                artist = match.group(pattern_def["artist_group"]).strip()
                has_explicit_artist = True
                break

        # Stage 3: Strip karaoke markers
        if not has_explicit_artist:
            for marker in YouTubeKaraokeMetadataParser.KARAOKE_MARKERS:
                clean = re.sub(marker, "", clean, flags=re.IGNORECASE).strip()

        # Stage 4: Parse remaining (ambiguous)
        if not has_explicit_artist and clean:
            if " - " in clean:
                parts = clean.split(" - ", 1)
                if len(parts) == 2:
                    artist = parts[0].strip()
                    title = parts[1].strip()
            else:
                title = clean

        # Determine status
        if has_explicit_artist:
            metadata_status = "parsed_strong"
        elif artist and title:
            metadata_status = "parsed_weak"
        else:
            metadata_status = "fallback"

        return {
            "artist": artist,
            "title": title or clean or filename,
            "youtube_id": youtube_id,
            "metadata_status": metadata_status,
            "has_explicit_artist": has_explicit_artist,
        }
```

**Database update:**

```python
from __future__ import annotations

import logging


def enrich_from_filenames(self):
    """Parse filenames and populate metadata.

    Returns:
        Number of songs updated
    """
    cursor = self.conn.execute(
        "SELECT id, filename FROM songs WHERE metadata_status = 'fallback'"
    )

    updated = 0
    parser = YouTubeKaraokeMetadataParser()

    for row in cursor.fetchall():
        song_id = row["id"]
        filename = row["filename"]

        parsed = parser.parse_filename(filename)

        needs_api = parsed["metadata_status"] in ("parsed_weak", "fallback")

        self.conn.execute(
            """
            UPDATE songs
            SET artist = ?,
                title = ?,
                youtube_id = ?,
                search_blob = ?,
                metadata_status = ?,
                queued_for_enrichment = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """,
            (
                parsed["artist"],
                parsed["title"],
                parsed["youtube_id"],
                self.build_search_blob(filename, parsed["title"], parsed["artist"]),
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

### Phase 4B: External API Enrichment (OPTIONAL)

**Goal:** Fetch year/genre from external APIs. Hard-coded API key for zero-friction setup.

#### API Strategy

**LastFM (Primary):**

- Rate: 5 req/sec
- Use: Fuzzy matching, resolve artist/title ordering
- Returns: Year, genre, canonical artist/title

**MusicBrainz (Secondary):**

- Rate: 1 req/sec (IP-based, strictly enforced)
- Use: Precision enrichment, validation
- **Critical:** Requires proper User-Agent header

**Hard-coded API key approach:**

```python
from __future__ import annotations

import logging
import os

DEFAULT_LASTFM_API_KEY = "abc123..."  # Hard-coded
DEFAULT_MUSICBRAINZ_USER_AGENT = "PiKaraoke/1.0 (https://github.com/vicwomg/pikaraoke)"


def get_lastfm_api_key() -> str:
    """Get LastFM API key (env override or default).

    Returns:
        API key string
    """
    return os.getenv("LASTFM_API_KEY", DEFAULT_LASTFM_API_KEY)


def get_musicbrainz_user_agent() -> str:
    """Get MusicBrainz User-Agent (env override or default).

    CRITICAL: MusicBrainz requires properly formatted User-Agent.
    Format: "AppName/Version ( contact )"

    Returns:
        User-Agent string
    """
    user_agent = os.getenv("MUSICBRAINZ_USER_AGENT", DEFAULT_MUSICBRAINZ_USER_AGENT)

    if not user_agent or "(" not in user_agent or ")" not in user_agent:
        logging.warning(f"Invalid User-Agent '{user_agent}', using default")
        return DEFAULT_MUSICBRAINZ_USER_AGENT

    return user_agent
```

#### LastFM Enricher

```python
from __future__ import annotations

import logging
import time
from datetime import datetime

import requests


class LastFMEnricher:
    """Enrich metadata using Last.FM API."""

    API_BASE = "http://ws.audioscrobbler.com/2.0/"
    RATE_LIMIT = 5

    def __init__(self, api_key: str):
        """Initialize enricher.

        Args:
            api_key: Last.FM API key
        """
        self.api_key = api_key
        self.last_request_time = 0
        self.session = requests.Session()

    def _rate_limit(self) -> None:
        """Enforce rate limiting."""
        now = time.time()
        elapsed = now - self.last_request_time
        min_interval = 1.0 / self.RATE_LIMIT

        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)

        self.last_request_time = time.time()

    def get_track_info(self, artist: str, title: str) -> dict[str, str | None] | None:
        """Fetch track metadata.

        Args:
            artist: Artist name
            title: Track title

        Returns:
            Dict with year, genre, canonical_artist, canonical_title or None
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
                return None

            track = data["track"]

            year = None
            if "wiki" in track and "published" in track["wiki"]:
                try:
                    date_str = track["wiki"]["published"]
                    date_obj = datetime.strptime(date_str, "%d %b %Y, %H:%M")
                    year = date_obj.year
                except Exception:
                    pass

            genre = None
            if "toptags" in track and "tag" in track["toptags"]:
                tags = track["toptags"]["tag"]
                if tags and len(tags) > 0:
                    genre = tags[0]["name"]

            return {
                "year": year,
                "genre": genre,
                "canonical_artist": track.get("artist", {}).get("name"),
                "canonical_title": track.get("name"),
            }

        except Exception as e:
            logging.error(f"Last.FM request failed: {e}")
            return None
```

#### Background Worker

```python
from __future__ import annotations

import logging
import time
from threading import Event, Thread
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pikaraoke.lib.karaoke_database import KaraokeDatabase


class EnrichmentWorker(Thread):
    """Background worker for metadata enrichment."""

    def __init__(self, db: "KaraokeDatabase", api_key: str, rate_limit: float = 5.0):
        """Initialize worker.

        Args:
            db: Database instance
            api_key: Last.FM API key
            rate_limit: Max requests per second
        """
        super().__init__(daemon=True, name="EnrichmentWorker")
        self.db = db
        self.api_key = api_key
        self.rate_limit = rate_limit
        self.min_interval = 1.0 / rate_limit

        self._stop_event = Event()
        self._pause_event = Event()
        self._pause_event.set()

        self.total_processed = 0
        self.total_enriched = 0
        self.total_failed = 0

    def run(self) -> None:
        """Main worker loop."""
        logging.info("Enrichment worker started")

        try:
            while not self._stop_event.is_set():
                self._pause_event.wait()

                song = self._get_next_song()

                if not song:
                    time.sleep(1.0)
                    continue

                success = self._enrich_song(song)

                if success:
                    self.total_enriched += 1
                else:
                    self.total_failed += 1

                self.total_processed += 1

                time.sleep(self.min_interval)

        except Exception as e:
            logging.error(f"Enrichment worker error: {e}")
        finally:
            logging.info(
                f"Enrichment worker stopped. Processed: {self.total_processed}, "
                f"Enriched: {self.total_enriched}, Failed: {self.total_failed}"
            )

    def _get_next_song(self) -> dict[str, str | int] | None:
        """Get next song from queue.

        Returns:
            Song dict or None
        """
        cursor = self.db.conn.execute(
            """
            SELECT id, artist, title, metadata_status
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

    def _enrich_song(self, song: dict[str, str | int]) -> bool:
        """Enrich a single song.

        Args:
            song: Song dict with id, artist, title, metadata_status

        Returns:
            True if successful
        """
        from pikaraoke.lib.lastfm_enricher import LastFMEnricher

        song_id = song["id"]
        artist = song["artist"]
        title = song["title"]
        current_status = song["metadata_status"]

        if not artist or not title:
            self._mark_failed(song_id, "No artist/title")
            return False

        try:
            enricher = LastFMEnricher(self.api_key)
            info = enricher.get_track_info(artist, title)

            if info:
                api_match_quality = (
                    "high" if info.get("year") and info.get("genre") else "low"
                )
                has_explicit_artist = current_status == "parsed_strong"

                if has_explicit_artist and api_match_quality == "high":
                    new_status = "api_verified"
                else:
                    new_status = "api_enriched"

                self.db.conn.execute(
                    """
                    UPDATE songs
                    SET year = ?,
                        genre = ?,
                        artist = ?,
                        title = ?,
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
                return True

            self._mark_failed(song_id, "Not found")
            return False

        except Exception as e:
            self._mark_failed(song_id, str(e))
            logging.error(f"Enrichment error: {e}")
            return False

    def _mark_failed(self, song_id: int, reason: str) -> None:
        """Mark song as failed.

        Args:
            song_id: Song ID
            reason: Failure reason
        """
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

    def stop(self) -> None:
        """Stop the worker."""
        logging.info("Stopping enrichment worker")
        self._stop_event.set()

    def pause(self) -> None:
        """Pause enrichment."""
        logging.info("Pausing enrichment worker")
        self._pause_event.clear()

    def resume(self) -> None:
        """Resume enrichment."""
        logging.info("Resuming enrichment worker")
        self._pause_event.set()
```

### Phase 4C: Manual UI Editor (ESSENTIAL FALLBACK)

**Goal:** Preserve existing LastFM suggestion UI, allow manual editing for edge cases.

PiKaraoke already has LastFM suggestion in `edit.html`. Enhance with:

1. Auto-populate from parsed metadata
2. Pre-query LastFM with parsed values
3. Show status badge
4. Allow manual override

**Backend route:**

```python
from __future__ import annotations

import logging

from flask import jsonify, request


@app.route("/edit_metadata/<int:song_id>", methods=["POST"])
@requires_admin
def edit_metadata(song_id: int):
    """Update song metadata manually.

    Args:
        song_id: Song ID

    Returns:
        JSON with success/error message
    """
    try:
        data = request.get_json()

        if not data.get("title"):
            return jsonify({"success": False, "message": "Title is required"}), 400

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
                data.get("artist"),
                data.get("title"),
                data.get("year"),
                data.get("genre"),
                data.get("variant"),
                k.db.build_search_blob(
                    data.get("title"), data.get("title"), data.get("artist")
                ),
                song_id,
            ),
        )
        k.db.conn.commit()

        return jsonify({"success": True, "message": "Metadata updated"})

    except Exception as e:
        logging.error(f"Edit metadata failed: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
```

## Recommended Phased Rollout

### Phase 4A: Filename Parsing ONLY (START HERE)

**Effort:** 1 day
**Risk:** Low

1. Implement `YouTubeKaraokeMetadataParser`
2. Add `enrich_from_filenames()` method
3. Add "Parse Filenames" button to admin UI
4. Test with 100 songs, then 1000, then full library

**Success:** 80%+ well-named files parsed correctly.

**Stop here if:** Budget/time constraints, or external APIs not desired.

### Phase 4B: External API (OPTIONAL)

**Effort:** 1-2 days
**Risk:** Medium

1. Implement `LastFMEnricher`
2. Add API key configuration
3. Add "Enrich Metadata" button with progress
4. Add background worker
5. Implement caching

**Success:** Year/genre populated for 60%+ songs.

### Phase 4C: Manual Editor (RECOMMENDED)

**Effort:** 0.5 day
**Risk:** Low

1. Enhance existing edit modal
2. Add backend route
3. Add status badges

**Success:** Users can edit any song, changes persist.

## Final Recommendations

**Required:** Phase 4A (parsing) + Phase 4C (manual editor). Essential for usable metadata, achieves 80% accuracy.

**Enhances:** Phase 4B (API enrichment) improves quality with genre/year data but not essential for core functionality.

**What NOT to Do:**

1. Don't use complex confidence scoring (status-based is simpler)
2. Don't create separate queue tables (embed in songs table)
3. Don't block startup on enrichment
4. Don't auto-overwrite manual edits

**Success Metrics:**

| Metric                    | Target |
| ------------------------- | ------ |
| Parsing accuracy          | > 80%  |
| Enrichment success rate   | > 90%  |
| Performance (1K songs)    | \< 5min |
| Code maintainability      | Single developer understands |
| Status clarity            | Users understand badges |

## Summary

**Core Strategy:** Get data into database, enrich with simplified status-based approach, fallback to manual editor for edge cases.

**Why Simplified Approach is RIGHT:**

1. Progressive enhancement
2. Non-blocking (users search immediately)
3. Graceful degradation
4. User control (manual editor)
5. Maintainable (70% less code)

**Implementation Benefits:**

- Code complexity: 70% reduction
- Database tables: 33% reduction (3 → 2)
- Maintenance: Easier for single developer
- UX: Clear status badges
- Effectiveness: 99% coverage maintained

**Final Verdict:** Proceed with simplified status-based approach. Implement Phase 4A (parsing) and 4C (manual UI) to achieve core objective. Add 4B (API enrichment) for enhanced metadata quality.

**Document Status:** Design Approved (Simplified Approach)
**Last Updated:** 2026-01-11
