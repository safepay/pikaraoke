"""Unit tests for the logical database backup and restore."""

import pytest

from pikaraoke.lib import db_backup
from pikaraoke.lib.db_backup import BackupVersionError
from pikaraoke.lib.karaoke_database import KaraokeDatabase


@pytest.fixture
def db(tmp_path):
    database = KaraokeDatabase(str(tmp_path / "test.db"))
    yield database
    database.close()


def _populate(db: KaraokeDatabase) -> None:
    """A small but complete graph: songs, a session, singers (one merged away),
    plays wired to all three, a favourite and a saved preference."""
    db.insert_songs(
        [
            {
                "file_path": "/songs/a---aaaaaaaaaaa.mp4",
                "youtube_id": "aaaaaaaaaaa",
                "format": "mp4",
            },
            {
                "file_path": "/songs/b---bbbbbbbbbbb.mp4",
                "youtube_id": "bbbbbbbbbbb",
                "format": "mp4",
            },
        ]
    )
    # A durable-column edit that only the backup can preserve.
    db.execute(
        "UPDATE songs SET year = 1984, genre = 'Pop', metadata_status = 'accepted' "
        "WHERE youtube_id = 'aaaaaaaaaaa'"
    )
    db.execute(
        "UPDATE songs SET suggested_year = 1999, suggested_genre = 'Rock', "
        "suggested_score = 80, metadata_country = 'US', metadata_status = 'suggested' "
        "WHERE youtube_id = 'bbbbbbbbbbb'"
    )
    db.execute("INSERT INTO sessions (uuid, name) VALUES ('sess-1', 'Friday')")
    # "Old" (id 1) is merged into "New" (id 2): the self-referential tombstone
    # that forces the restore to defer foreign keys.
    db.execute("INSERT INTO singers (name) VALUES ('Old')")
    db.execute("INSERT INTO singers (name) VALUES ('New')")
    db.execute("UPDATE singers SET merged_into = 2 WHERE id = 1")
    db.execute(
        "INSERT INTO plays (session_id, song_id, youtube_id, song_title, performer, "
        "singer_id, semitones, completed) VALUES (1, 1, 'aaaaaaaaaaa', 'A', 'New', 2, 2, 1)"
    )
    db.execute(
        "INSERT INTO singer_songs (singer_id, song_id, youtube_id, song_title, starred) "
        "VALUES (2, 1, 'aaaaaaaaaaa', 'A', 1)"
    )
    db.execute(
        "INSERT INTO singer_preferences (singer_id, key, value) VALUES (2, 'language', 'en')"
    )


def _counts(db: KaraokeDatabase) -> dict[str, int]:
    return {t: db.query(f"SELECT COUNT(*) FROM {t}")[0][0] for t in db_backup.DURABLE_TABLES}


class TestDumpContents:
    def test_header_names_schema_app_version_and_time(self, db):
        dump = db_backup.build_dump(db)
        assert dump["schema_version"] == db.schema_version
        assert dump["app_version"]
        assert dump["created_at"]

    def test_covers_every_durable_table(self, db):
        _populate(db)
        dump = db_backup.build_dump(db)
        assert set(dump["tables"]) == set(db_backup.DURABLE_TABLES)
        assert len(dump["tables"]["songs"]) == 2
        assert len(dump["tables"]["singers"]) == 2

    def test_excludes_the_regenerable_metadata_table(self, db):
        assert "metadata" not in db_backup.DURABLE_TABLES

    def test_rows_carry_their_ids_and_durable_columns(self, db):
        _populate(db)
        tables = db_backup.build_dump(db)["tables"]
        song_a = next(r for r in tables["songs"] if r["youtube_id"] == "aaaaaaaaaaa")
        assert song_a["id"] == 1
        assert song_a["year"] == 1984
        assert song_a["metadata_status"] == "accepted"


class TestRoundTrip:
    def test_restores_every_row_after_a_wipe(self, db):
        _populate(db)
        dump = db_backup.load_dump(db_backup.dump_to_json(db_backup.build_dump(db)))
        before = _counts(db)

        db.replace_tables({t: [] for t in db_backup.DURABLE_TABLES})
        assert _counts(db) == {t: 0 for t in db_backup.DURABLE_TABLES}

        db_backup.restore_dump(db, dump)
        assert _counts(db) == before

    def test_foreign_keys_restore_intact(self, db):
        _populate(db)
        dump = db_backup.build_dump(db)
        db.replace_tables({t: [] for t in db_backup.DURABLE_TABLES})
        db_backup.restore_dump(db, dump)

        play = db.query(
            "SELECT p.session_id, p.song_id, p.singer_id, s.uuid, so.youtube_id, si.name "
            "FROM plays p "
            "JOIN sessions s ON s.id = p.session_id "
            "JOIN songs so ON so.id = p.song_id "
            "JOIN singers si ON si.id = p.singer_id"
        )
        assert len(play) == 1
        assert play[0]["uuid"] == "sess-1"
        assert play[0]["youtube_id"] == "aaaaaaaaaaa"
        assert play[0]["name"] == "New"

    def test_self_referential_merge_tombstone_resolves(self, db):
        _populate(db)
        dump = db_backup.build_dump(db)
        db.replace_tables({t: [] for t in db_backup.DURABLE_TABLES})
        db_backup.restore_dump(db, dump)
        row = db.query("SELECT merged_into FROM singers WHERE name = 'Old'")
        assert row[0]["merged_into"] == 2

    def test_restore_is_a_full_replacement_not_a_merge(self, db):
        _populate(db)
        dump = db_backup.build_dump(db)
        # A row present only in the live DB must be gone after a restore.
        db.execute("INSERT INTO sessions (uuid, name) VALUES ('stale', 'Gone')")
        db_backup.restore_dump(db, dump)
        assert db.query("SELECT COUNT(*) FROM sessions WHERE uuid = 'stale'")[0][0] == 0
        assert _counts(db)["sessions"] == 1

    def test_metadata_table_survives_a_restore(self, db):
        _populate(db)
        db.set_metadata("last_scan_directory", "/songs")
        db_backup.restore_dump(db, db_backup.build_dump(db))
        assert db.get_metadata("last_scan_directory") == "/songs"

    def test_autoincrement_advances_past_reloaded_ids(self, db):
        _populate(db)
        dump = db_backup.build_dump(db)
        db.replace_tables({t: [] for t in db_backup.DURABLE_TABLES})
        db_backup.restore_dump(db, dump)
        db.execute("INSERT INTO sessions (uuid, name) VALUES ('sess-2', 'Saturday')")
        new_id = db.query("SELECT id FROM sessions WHERE uuid = 'sess-2'")[0][0]
        assert new_id == 2  # not 1, which the restored row already holds


class TestVersionGuard:
    def test_a_newer_schema_is_refused(self, db):
        dump = db_backup.build_dump(db)
        dump["schema_version"] = db.schema_version + 1
        with pytest.raises(BackupVersionError):
            db_backup.restore_dump(db, dump)

    def test_a_missing_schema_version_is_refused(self, db):
        dump = db_backup.build_dump(db)
        del dump["schema_version"]
        with pytest.raises(BackupVersionError):
            db_backup.restore_dump(db, dump)

    def test_the_current_schema_loads(self, db):
        _populate(db)
        dump = db_backup.build_dump(db)
        db_backup.restore_dump(db, dump)  # no raise

    def test_an_older_dump_missing_a_column_loads_with_defaults(self, db):
        _populate(db)
        dump = db_backup.build_dump(db)
        dump["schema_version"] = db.schema_version - 1
        for row in dump["tables"]["songs"]:
            row.pop("genre", None)  # a column an older dump would not carry
        db_backup.restore_dump(db, dump)
        # The row loads; the dropped column falls back to its schema default (NULL).
        assert db.query("SELECT genre FROM songs WHERE youtube_id = 'aaaaaaaaaaa'")[0][0] is None
        assert _counts(db)["songs"] == 2


class TestFingerprint:
    def test_ignores_the_header_timestamp(self, db):
        _populate(db)
        one = db_backup.build_dump(db)
        two = db_backup.build_dump(db)
        assert db_backup.dump_fingerprint(one) == db_backup.dump_fingerprint(two)

    def test_changes_when_a_row_changes(self, db):
        _populate(db)
        before = db_backup.dump_fingerprint(db_backup.build_dump(db))
        db.execute("INSERT INTO sessions (uuid, name) VALUES ('sess-2', 'Saturday')")
        after = db_backup.dump_fingerprint(db_backup.build_dump(db))
        assert before != after
