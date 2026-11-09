"""Restore-then-resync: the durable stratum survives a loss and relinks to files.

Exercises db_backup and LibraryScanner together against real files on disk,
without constructing the full managed Karaoke instance.
"""

import os

import pytest

from pikaraoke.lib import db_backup
from pikaraoke.lib.karaoke_database import KaraokeDatabase
from pikaraoke.lib.library_scanner import LibraryScanner


def _make_song(directory, name):
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write("stub")
    return path


def _populate_durable(db):
    """Tag one song and give it a play through a session and singer."""
    db.execute(
        "UPDATE songs SET year = 1984, metadata_status = 'accepted' WHERE youtube_id = ?",
        ("aaaaaaaaaaa",),
    )
    db.execute("INSERT INTO sessions (uuid, name) VALUES ('s', 'Friday')")
    db.execute("INSERT INTO singers (name) VALUES ('Mel')")
    song_id = db.query("SELECT id FROM songs WHERE youtube_id = ?", ("aaaaaaaaaaa",))[0][0]
    singer_id = db.query("SELECT id FROM singers WHERE name = 'Mel'")[0][0]
    session_id = db.query("SELECT id FROM sessions WHERE uuid = 's'")[0][0]
    db.execute(
        "INSERT INTO plays (session_id, song_id, youtube_id, song_title, performer, singer_id) "
        "VALUES (?, ?, 'aaaaaaaaaaa', 'A', 'Mel', ?)",
        (session_id, song_id, singer_id),
    )


@pytest.fixture
def songs_dir(tmp_path):
    directory = str(tmp_path / "songs")
    _make_song(directory, "A---aaaaaaaaaaa.mp4")
    _make_song(directory, "B---bbbbbbbbbbb.mp4")
    return directory


def _dump_from_scan(tmp_path, songs_dir):
    source = KaraokeDatabase(str(tmp_path / "source.db"))
    LibraryScanner(source).scan(songs_dir)
    _populate_durable(source)
    dump = db_backup.build_dump(source)
    source.close()
    return dump


def test_restore_then_resync_keeps_durable_data(tmp_path, songs_dir):
    dump = _dump_from_scan(tmp_path, songs_dir)

    # A fresh, empty database stands in for a lost one. Restore, then resync
    # against the files still on disk at their original paths.
    fresh = KaraokeDatabase(str(tmp_path / "fresh.db"))
    db_backup.restore_dump(fresh, dump)
    result = LibraryScanner(fresh).scan(songs_dir)

    assert result.added == 0 and result.deleted == 0  # files matched directly
    assert fresh.get_song_count() == 2
    assert fresh.query("SELECT year FROM songs WHERE youtube_id = 'aaaaaaaaaaa'")[0][0] == 1984
    # The whole graph resolves: the play joins its song, session and singer.
    joined = fresh.query(
        "SELECT si.name FROM plays p JOIN songs s ON s.id = p.song_id "
        "JOIN sessions se ON se.id = p.session_id JOIN singers si ON si.id = p.singer_id"
    )
    assert joined[0]["name"] == "Mel"
    fresh.close()


def test_resync_relinks_files_moved_to_a_new_folder(tmp_path, songs_dir):
    dump = _dump_from_scan(tmp_path, songs_dir)

    # The files come back under a different folder, same basenames.
    moved_dir = str(tmp_path / "usb" / "songs")
    _make_song(moved_dir, "A---aaaaaaaaaaa.mp4")
    _make_song(moved_dir, "B---bbbbbbbbbbb.mp4")

    fresh = KaraokeDatabase(str(tmp_path / "fresh.db"))
    db_backup.restore_dump(fresh, dump)
    result = LibraryScanner(fresh).scan(moved_dir)

    assert result.moved == 2 and result.added == 0 and result.deleted == 0
    assert fresh.get_song_count() == 2
    # Durable data kept, and the path now points at the new folder.
    row = fresh.query("SELECT file_path, year FROM songs WHERE youtube_id = 'aaaaaaaaaaa'")[0]
    assert row["file_path"].startswith(moved_dir)
    assert row["year"] == 1984
    fresh.close()


def test_resync_drops_a_genuinely_deleted_file_but_keeps_its_play(tmp_path, songs_dir):
    dump = _dump_from_scan(tmp_path, songs_dir)
    # Only one of the two files comes back; the tagged one (A) is genuinely gone.
    present_only = str(tmp_path / "partial")
    _make_song(present_only, "B---bbbbbbbbbbb.mp4")

    fresh = KaraokeDatabase(str(tmp_path / "fresh.db"))
    db_backup.restore_dump(fresh, dump)
    # Directory changed (partial/ vs songs/), so the circuit breaker is bypassed
    # and the single real deletion is applied.
    LibraryScanner(fresh).scan(present_only)

    assert fresh.get_song_count() == 1
    # The song row is gone; its play stays on the leaderboard with a NULL song_id.
    play = fresh.query("SELECT song_id, youtube_id FROM plays WHERE youtube_id = 'aaaaaaaaaaa'")
    assert len(play) == 1
    assert play[0]["song_id"] is None
    fresh.close()
