"""Background lookup of song metadata, so the renamer never calls the network."""

import logging
from datetime import datetime, timezone

from gevent import Greenlet, sleep, spawn

from pikaraoke.lib.events import EventSystem
from pikaraoke.lib.karaoke_database import KaraokeDatabase
from pikaraoke.lib.metadata_parser import has_artist_title_separator, regex_tidy
from pikaraoke.lib.preference_manager import PreferenceManager
from pikaraoke.lib.song_manager import SongManager

# Longer than ITUNES_RATE_LIMIT so the edit page's Suggest button, which shares
# the provider's class-level gate, usually wins it.
LOOKUP_INTERVAL = 5.0
IDLE_INTERVAL = 30.0
MAX_ATTEMPTS = 3
# Yield while classifying, which is pure CPU over the whole library.
_CLASSIFY_CHUNK = 200


class MetadataLookupWorker:
    """Greenlet that fills in each song's suggested name, year and genre."""

    def __init__(
        self, db: KaraokeDatabase, preferences: PreferenceManager, events: EventSystem
    ) -> None:
        self._db = db
        self._preferences = preferences
        self._events = events
        self._worker: Greenlet | None = None

    def start(self) -> None:
        """Start the lookup greenlet.

        A greenlet rather than a thread for the reason DownloadManager gives: a
        second hub races the main one at WSGIServer startup.
        """
        self._worker = spawn(self._run)

    def stop(self) -> None:
        if self._worker is not None:
            self._worker.kill(block=False)
            self._worker = None

    @property
    def enabled(self) -> bool:
        return bool(self._preferences.get_or_default("enable_metadata_lookup"))

    def _run(self) -> None:
        while True:
            if not self.enabled:
                sleep(IDLE_INTERVAL)
                continue
            # Read before the backlog, so anything inserted afterwards is an
            # arrival rather than a row this sweep already holds.
            started = _utc_now()
            backlog = self._prioritised_paths()
            if not backlog:
                sleep(IDLE_INTERVAL)
                continue
            for path in backlog:
                if not self.enabled:
                    break
                self._sweep_arrivals(started)
                self._process(path)

    def _sweep_arrivals(self, since: str) -> None:
        """Look up songs the library gained mid-sweep, before continuing.

        A download nobody is waiting on is not why the feature exists. Left in
        the backlog a new song waits out the whole pass, and a YouTube name that
        tidies cleanly sorts to the very back of it.
        """
        for path in self._db.get_paths_awaiting_lookup(MAX_ATTEMPTS, added_since=since):
            if not self.enabled:
                return
            self._process(path)

    def _process(self, path: str) -> None:
        self._look_up(path)
        # Per song, so the settings page counts up while it is watched. The
        # event carries no payload; only an open settings page acts on it, by
        # refetching one grouped count.
        self._events.emit("metadata_lookup_progress")
        sleep(LOOKUP_INTERVAL)

    def _prioritised_paths(self) -> list[str]:
        """Pending paths, unusable names first.

        A name that does not resolve to "Artist - Title" is what an admin opens
        the renamer to fix; the rest read acceptably already and are only being
        upgraded, so they can wait out a sweep measured in hours.
        """
        paths = self._db.get_paths_awaiting_lookup(MAX_ATTEMPTS)
        unusable, cosmetic = [], []
        for index, path in enumerate(paths):
            stem = SongManager.filename_from_path(path, tidy=False)
            target = unusable if not has_artist_title_separator(regex_tidy(stem)) else cosmetic
            target.append(path)
            if index % _CLASSIFY_CHUNK == 0:
                sleep(0)
        return unusable + cosmetic

    def _look_up(self, path: str) -> None:
        # Imported here, not at module scope: this module reaches Karaoke's
        # import list, and pulling in requests (so ssl, so urllib3) before
        # app.py monkey-patches would leave those modules unpatched.
        from pikaraoke.lib.metadata_providers import (
            ITUNES_MAX_RETRIES,
            get_provider,
            suggest_metadata,
        )

        country = self._preferences.get_or_default("itunes_search_country")
        artist_first = self._preferences.get_or_default("suggestion_name_order") == "artist_title"
        # The raw stem: suggest_metadata tidies its own input, and a display
        # preference must never reach a stored suggestion.
        stem = SongManager.filename_from_path(path, tidy=False)
        try:
            results = suggest_metadata(
                stem,
                provider=get_provider(self._preferences, country=country),
                artist_first=artist_first,
                max_retries=ITUNES_MAX_RETRIES,
            )
        except Exception:
            # Broad: one malformed response must not kill the sweep. The attempt
            # is still counted, or a song that always throws is retried forever.
            logging.exception("Metadata lookup failed for %s", path)
            self._db.record_failed_attempt(path)
            return
        best = results[0] if results else None
        if best is None or not best.get("artist") or not best.get("title"):
            self._db.mark_no_match(path, country)
            return
        self._db.save_suggestion(
            path,
            artist=best["artist"],
            title=best["title"],
            year=_as_year(best.get("year")),
            genre=best.get("genre") or None,
            score=best["score"],
            country=country,
        )


def _utc_now() -> str:
    """Now, matching the format SQLite's CURRENT_TIMESTAMP writes to created_at."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _as_year(value: object) -> int | None:
    try:
        return int(str(value)[:4])
    except (TypeError, ValueError):
        return None
