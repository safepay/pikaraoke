"""Unit tests for BackupManager (the backups directory)."""

import os

import pytest

from pikaraoke.lib import db_backup
from pikaraoke.lib.backup_manager import BackupManager, is_backup_filename
from pikaraoke.lib.karaoke_database import KaraokeDatabase


@pytest.fixture
def db(tmp_path):
    database = KaraokeDatabase(str(tmp_path / "test.db"))
    database.insert_songs(
        [{"file_path": "/songs/a---aaaaaaaaaaa.mp4", "youtube_id": "aaaaaaaaaaa", "format": "mp4"}]
    )
    yield database
    database.close()


@pytest.fixture
def backup_dir(tmp_path):
    return str(tmp_path / "backups")


def _manager(db, backup_dir, keep=10):
    return BackupManager(db, backup_dir, get_keep_count=lambda: keep)


def _touch(backup_dir, name, songs=0):
    os.makedirs(backup_dir, exist_ok=True)
    dump = {"schema_version": 3, "created_at": name, "tables": {"songs": [{}] * songs}}
    with open(os.path.join(backup_dir, name), "w", encoding="utf-8") as f:
        f.write(db_backup.dump_to_json(dump))


class TestCreateBackup:
    def test_writes_a_named_dump_that_parses(self, db, backup_dir):
        path = _manager(db, backup_dir).create_backup()
        assert os.path.isfile(path)
        assert is_backup_filename(os.path.basename(path))
        dump = db_backup.load_dump(open(path, encoding="utf-8").read())
        assert dump["schema_version"] == db.schema_version
        assert len(dump["tables"]["songs"]) == 1

    def test_creates_the_directory_on_demand(self, db, backup_dir):
        assert not os.path.exists(backup_dir)
        _manager(db, backup_dir).create_backup()
        assert os.path.isdir(backup_dir)

    def test_two_backups_do_not_collide(self, db, backup_dir):
        mgr = _manager(db, backup_dir)
        first, second = mgr.create_backup(), mgr.create_backup()
        assert first != second
        assert len(os.listdir(backup_dir)) == 2


class TestStartupBackup:
    def test_writes_on_first_run(self, db, backup_dir):
        assert _manager(db, backup_dir).startup_backup() is not None
        assert len(os.listdir(backup_dir)) == 1

    def test_skips_when_unchanged(self, db, backup_dir):
        mgr = _manager(db, backup_dir)
        mgr.startup_backup()
        assert mgr.startup_backup() is None
        assert len(os.listdir(backup_dir)) == 1

    def test_writes_again_after_a_change(self, db, backup_dir):
        mgr = _manager(db, backup_dir)
        mgr.startup_backup()
        db.execute("INSERT INTO sessions (uuid, name) VALUES ('s', 'S')")
        assert mgr.startup_backup() is not None
        assert len(os.listdir(backup_dir)) == 2


class TestListBackups:
    def test_newest_first_with_metadata(self, backup_dir, db):
        _touch(backup_dir, "pikaraoke-backup-20260101-120000.json", songs=3)
        _touch(backup_dir, "pikaraoke-backup-20260102-120000.json", songs=5)
        rows = _manager(db, backup_dir).list_backups()
        assert [r["name"] for r in rows] == [
            "pikaraoke-backup-20260102-120000.json",
            "pikaraoke-backup-20260101-120000.json",
        ]
        assert rows[0]["song_count"] == 5
        assert rows[0]["size"] > 0

    def test_unreadable_file_is_listed_without_counts(self, backup_dir, db):
        os.makedirs(backup_dir, exist_ok=True)
        with open(os.path.join(backup_dir, "pikaraoke-backup-20260101-120000.json"), "w") as f:
            f.write("not json")
        rows = _manager(db, backup_dir).list_backups()
        assert len(rows) == 1
        assert rows[0]["song_count"] is None

    def test_ignores_foreign_files(self, backup_dir, db):
        os.makedirs(backup_dir, exist_ok=True)
        open(os.path.join(backup_dir, "notes.txt"), "w").close()
        _touch(backup_dir, "pikaraoke-backup-20260101-120000.json")
        rows = _manager(db, backup_dir).list_backups()
        assert len(rows) == 1


class TestPrune:
    def test_keeps_the_newest_n(self, backup_dir, db):
        for day in range(1, 6):
            _touch(backup_dir, f"pikaraoke-backup-2026010{day}-120000.json")
        _manager(db, backup_dir, keep=3).prune()
        remaining = sorted(os.listdir(backup_dir))
        assert remaining == [
            "pikaraoke-backup-20260103-120000.json",
            "pikaraoke-backup-20260104-120000.json",
            "pikaraoke-backup-20260105-120000.json",
        ]

    def test_create_backup_prunes(self, db, backup_dir):
        for day in range(1, 4):
            _touch(backup_dir, f"pikaraoke-backup-2026010{day}-120000.json")
        _manager(db, backup_dir, keep=2).create_backup()
        assert len(os.listdir(backup_dir)) == 2


class TestPathSafety:
    def test_rejects_traversal_and_foreign_names(self, db, backup_dir):
        mgr = _manager(db, backup_dir)
        for bad in ("../secret.json", "pikaraoke-backup-x/../../etc", "notes.txt", "backup.json"):
            with pytest.raises(ValueError):
                mgr.path_for(bad)

    def test_round_trips_a_valid_name(self, db, backup_dir):
        mgr = _manager(db, backup_dir)
        path = mgr.create_backup()
        dump = mgr.read_backup(os.path.basename(path))
        assert dump["schema_version"] == db.schema_version
