"""Unit tests for MetadataLookupWorker."""

import subprocess
import sys
import time
from unittest.mock import patch

import pytest

from pikaraoke.lib.events import EventSystem
from pikaraoke.lib.karaoke_database import KaraokeDatabase
from pikaraoke.lib.metadata_lookup_worker import MetadataLookupWorker
from pikaraoke.lib.preference_manager import PreferenceManager


def _suggestion(**overrides):
    base = {
        "artist": "Beyonce",
        "title": "Halo",
        "year": "2008",
        "genre": "Pop",
        "source": "itunes",
        "display": "Beyonce - Halo",
        "score": 98,
    }
    return {**base, **overrides}


@pytest.fixture
def db(tmp_path):
    d = KaraokeDatabase(str(tmp_path / "test.db"))
    yield d
    d.close()


@pytest.fixture
def preferences(tmp_path):
    return PreferenceManager(config_file_path=str(tmp_path / "config.ini"))


@pytest.fixture
def worker(db, preferences):
    preferences.set("enable_metadata_lookup", True)
    return MetadataLookupWorker(db=db, preferences=preferences, events=EventSystem())


def _add(db, *paths):
    db.insert_songs([{"file_path": p, "youtube_id": None, "format": "mp4"} for p in paths])


class TestLookup:
    def test_a_match_is_stored_and_the_song_advances(self, worker, db):
        _add(db, "/songs/halo.mp4")
        with patch(
            "pikaraoke.lib.metadata_providers.suggest_metadata", return_value=[_suggestion()]
        ):
            worker._look_up("/songs/halo.mp4")
        row = db.query(
            "SELECT artist, title, suggested_year, suggested_genre, suggested_score, "
            "metadata_status FROM songs WHERE file_path = ?",
            ("/songs/halo.mp4",),
        )[0]
        assert tuple(row) == ("Beyonce", "Halo", 2008, "Pop", 98, "suggested")

    def test_no_results_lands_on_no_match(self, worker, db):
        _add(db, "/songs/obscure.mp4")
        with patch("pikaraoke.lib.metadata_providers.suggest_metadata", return_value=[]):
            worker._look_up("/songs/obscure.mp4")
        assert db.get_metadata_status_counts()["no_match"] == 1

    def test_a_half_filled_result_is_not_a_match(self, worker, db):
        _add(db, "/songs/partial.mp4")
        with patch(
            "pikaraoke.lib.metadata_providers.suggest_metadata",
            return_value=[_suggestion(title="")],
        ):
            worker._look_up("/songs/partial.mp4")
        assert db.get_metadata_status_counts()["no_match"] == 1

    def test_a_failure_counts_the_attempt_and_stays_pending(self, worker, db):
        _add(db, "/songs/boom.mp4")
        with patch(
            "pikaraoke.lib.metadata_providers.suggest_metadata", side_effect=RuntimeError("x")
        ):
            worker._look_up("/songs/boom.mp4")
        row = db.query(
            "SELECT metadata_status, enrichment_attempts FROM songs WHERE file_path = ?",
            ("/songs/boom.mp4",),
        )[0]
        assert tuple(row) == ("pending", 1)

    def test_a_missing_year_is_stored_as_null(self, worker, db):
        _add(db, "/songs/undated.mp4")
        with patch(
            "pikaraoke.lib.metadata_providers.suggest_metadata",
            return_value=[_suggestion(year="")],
        ):
            worker._look_up("/songs/undated.mp4")
        assert (
            db.query(
                "SELECT suggested_year FROM songs WHERE file_path = ?", ("/songs/undated.mp4",)
            )[0][0]
            is None
        )


class TestTheNameFedToTheProvider:
    """The raw stem, never a tidied or preference-dependent form: a stored
    suggestion must not depend on a display setting."""

    def test_the_raw_stem_is_the_query(self, worker, db):
        path = "/songs/Beyonce - Halo (Official Video)---dQw4w9WgXcQ.mp4"
        _add(db, path)
        with patch(
            "pikaraoke.lib.metadata_providers.suggest_metadata", return_value=[_suggestion()]
        ) as mock:
            worker._look_up(path)
        assert mock.call_args.args[0] == "Beyonce - Halo (Official Video)"

    def test_the_title_tidy_preference_does_not_reach_the_query(self, worker, db, preferences):
        path = "/songs/Beyonce - Halo (Official Video)---dQw4w9WgXcQ.mp4"
        _add(db, path)
        preferences.set("enable_title_tidy", True)
        with patch(
            "pikaraoke.lib.metadata_providers.suggest_metadata", return_value=[_suggestion()]
        ) as mock:
            worker._look_up(path)
        assert mock.call_args.args[0] == "Beyonce - Halo (Official Video)"

    def test_the_name_order_preference_is_passed_through(self, worker, db, preferences):
        _add(db, "/songs/halo.mp4")
        preferences.set("suggestion_name_order", "title_artist")
        with patch(
            "pikaraoke.lib.metadata_providers.suggest_metadata", return_value=[_suggestion()]
        ) as mock:
            worker._look_up("/songs/halo.mp4")
        assert mock.call_args.kwargs["artist_first"] is False

    def test_the_storefront_is_recorded_with_the_result(self, worker, db, preferences):
        _add(db, "/songs/halo.mp4")
        preferences.set("itunes_search_country", "GB")
        with patch(
            "pikaraoke.lib.metadata_providers.suggest_metadata", return_value=[_suggestion()]
        ):
            worker._look_up("/songs/halo.mp4")
        assert (
            db.query(
                "SELECT metadata_country FROM songs WHERE file_path = ?", ("/songs/halo.mp4",)
            )[0][0]
            == "GB"
        )


class TestPriority:
    def test_unusable_names_are_looked_up_first(self, worker, db):
        _add(
            db,
            "/songs/Beyonce - Halo.mp4",
            "/songs/some_rip_003.mp4",
            "/songs/ABBA - Waterloo.mp4",
        )
        assert worker._prioritised_paths()[0] == "/songs/some_rip_003.mp4"

    def test_a_youtube_name_that_tidies_cleanly_is_not_urgent(self, worker, db):
        _add(
            db,
            "/songs/Beyonce - Halo (Official Video)---dQw4w9WgXcQ.mp4",
            "/songs/rip.mp4",
        )
        assert worker._prioritised_paths() == [
            "/songs/rip.mp4",
            "/songs/Beyonce - Halo (Official Video)---dQw4w9WgXcQ.mp4",
        ]

    def test_songs_already_looked_up_are_not_offered(self, worker, db):
        _add(db, "/songs/a.mp4", "/songs/b.mp4")
        db.save_suggestion("/songs/a.mp4", "A", "B", 2000, "Pop", 98, "US")
        assert worker._prioritised_paths() == ["/songs/b.mp4"]


class TestNewSongs:
    """A song added to the library is looked up with no admin action. During a
    sweep that means jumping the backlog, which it would otherwise sit at the
    back of -- a YouTube name that tidies cleanly sorts to the cosmetic tier."""

    def test_a_newly_added_song_is_picked_up(self, worker, db):
        _add(db, "/songs/just_downloaded.mp4")
        assert worker._prioritised_paths() == ["/songs/just_downloaded.mp4"]

    def test_a_song_added_before_the_sweep_is_not_an_arrival(self, db):
        _add(db, "/songs/old.mp4")
        later = "9999-01-01 00:00:00"
        assert db.get_paths_awaiting_lookup(3, added_since=later) == []

    def test_a_song_added_after_the_sweep_started_is_an_arrival(self, db):
        _add(db, "/songs/new.mp4")
        earlier = "0001-01-01 00:00:00"
        assert db.get_paths_awaiting_lookup(3, added_since=earlier) == ["/songs/new.mp4"]

    def test_an_arrival_is_looked_up_without_waiting_for_the_backlog(self, worker, db, monkeypatch):
        monkeypatch.setattr("pikaraoke.lib.metadata_lookup_worker.LOOKUP_INTERVAL", 0)
        _add(db, "/songs/backlog.mp4", "/songs/arrived.mp4")
        with patch(
            "pikaraoke.lib.metadata_providers.suggest_metadata", return_value=[_suggestion()]
        ):
            worker._sweep_arrivals("0001-01-01 00:00:00")
        assert db.get_metadata_status_counts()["pending"] == 0

    def test_arrivals_stop_when_the_preference_is_turned_off(
        self, worker, db, preferences, monkeypatch
    ):
        monkeypatch.setattr("pikaraoke.lib.metadata_lookup_worker.LOOKUP_INTERVAL", 0)
        _add(db, "/songs/a.mp4", "/songs/b.mp4")
        preferences.set("enable_metadata_lookup", False)
        with patch(
            "pikaraoke.lib.metadata_providers.suggest_metadata", return_value=[_suggestion()]
        ):
            worker._sweep_arrivals("0001-01-01 00:00:00")
        assert db.get_metadata_status_counts()["pending"] == 2


class TestTheEnabledPreference:
    def test_off_by_default(self, db, preferences):
        w = MetadataLookupWorker(db=db, preferences=preferences, events=EventSystem())
        assert w.enabled is False

    def test_reflects_a_change_without_a_restart(self, worker, preferences):
        assert worker.enabled is True
        preferences.set("enable_metadata_lookup", False)
        assert worker.enabled is False


class TestImportSideEffects:
    """metadata_providers imports requests at module scope, and this module is on
    Karaoke's import list. Pulling requests (so ssl) in before app.py patches
    would leave it unpatched -- gevent warns, and the sockets misbehave."""

    def test_importing_karaoke_does_not_load_requests(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys, pikaraoke.karaoke;"
                " print('requests' in sys.modules or 'urllib3.util' in sys.modules)",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout.strip() == "False"


class TestPace:
    """The settings page multiplies this by the pending count for its estimate,
    so it has to follow the hardware rather than a constant: a Pi over wifi is
    not a Windows desktop on ethernet."""

    def test_starts_from_the_seeded_estimate(self, worker):
        assert worker.seconds_per_lookup == pytest.approx(4.5)

    def test_follows_what_the_worker_actually_manages(self, worker, db, monkeypatch):
        monkeypatch.setattr("pikaraoke.lib.metadata_lookup_worker.LOOKUP_INTERVAL", 0)
        _add(db, *[f"/songs/{n}.mp4" for n in range(30)])
        with patch(
            "pikaraoke.lib.metadata_providers.suggest_metadata", return_value=[_suggestion()]
        ):
            for path in worker._prioritised_paths():
                worker._process(path)
        # A mocked lookup returns instantly, so the estimate should fall well
        # below the seed rather than staying pinned to it.
        assert worker.seconds_per_lookup < 1.0

    def test_one_slow_response_does_not_swing_the_estimate(self, worker, db, monkeypatch):
        monkeypatch.setattr("pikaraoke.lib.metadata_lookup_worker.LOOKUP_INTERVAL", 0)
        _add(db, "/songs/slow.mp4")

        def slow(*args, **kwargs):
            time.sleep(0.4)
            return [_suggestion()]

        with patch("pikaraoke.lib.metadata_providers.suggest_metadata", side_effect=slow):
            worker._process("/songs/slow.mp4")
        assert worker.seconds_per_lookup == pytest.approx(4.5, abs=1.0)
