"""Route tests for the backup, restore and reset-database API."""

import io
import json
import os

import pytest

from pikaraoke.lib import db_backup
from pikaraoke.lib.backup_manager import BackupManager
from pikaraoke.lib.karaoke_database import KaraokeDatabase
from pikaraoke.routes.backup_api import backup_api_bp

from ..conftest import make_route_app


class FakeKaraoke:
    """A karaoke whose restore/reset act on a real database, so the routes can
    be tested end to end without the full managed instance."""

    def __init__(self, db: KaraokeDatabase, backup_manager: BackupManager) -> None:
        self.db = db
        self.backup_manager = backup_manager
        self.restored = False
        self.reset_called = False

    def restore_database(self, dump: dict) -> None:
        db_backup.restore_dump(self.db, dump)
        self.restored = True

    def reset_database(self) -> None:
        self.db.clear_all_tables()
        self.reset_called = True


@pytest.fixture
def db(tmp_path):
    database = KaraokeDatabase(str(tmp_path / "test.db"))
    database.insert_songs(
        [{"file_path": "/songs/a---aaaaaaaaaaa.mp4", "youtube_id": "aaaaaaaaaaa", "format": "mp4"}]
    )
    database.execute("INSERT INTO sessions (uuid, name) VALUES ('s', 'Friday')")
    yield database
    database.close()


@pytest.fixture
def manager(db, tmp_path):
    return BackupManager(db, str(tmp_path / "backups"), get_keep_count=lambda: 10)


@pytest.fixture
def karaoke(db, manager):
    return FakeKaraoke(db, manager)


@pytest.fixture
def app(karaoke):
    application = make_route_app(backup_api_bp, [])
    application.config["KARAOKE_INSTANCE"] = karaoke
    return application


def _backup_count(manager):
    return len(manager.list_backups())


class TestListAndBackupNow:
    def test_list_reports_backups_and_path(self, client, manager):
        manager.create_backup()
        resp = client.post("/api/backups/list")
        body = resp.get_json()
        assert len(body["backups"]) == 1
        assert body["path"] == manager.backup_dir

    def test_backup_now_writes_a_server_file(self, client, manager):
        resp = client.post("/api/backups")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        assert body["name"].endswith(".json")
        assert _backup_count(manager) == 1


class TestDownload:
    def test_downloads_an_existing_backup(self, client, manager):
        path = manager.create_backup()
        name = os.path.basename(path)
        resp = client.post(f"/api/backups/{name}/download")
        assert resp.status_code == 200
        assert "attachment" in resp.headers["Content-Disposition"]
        assert json.loads(resp.data)["schema_version"]

    def test_missing_backup_is_404(self, client):
        resp = client.post("/api/backups/pikaraoke-backup-20260101-120000.json/download")
        assert resp.status_code == 404

    def test_invalid_download_name_is_400(self, client):
        resp = client.post("/api/backups/evil.json/download")
        assert resp.status_code == 400


class TestRestore:
    def test_restore_from_server_backup_backs_up_first(self, client, karaoke, manager, db):
        path = manager.create_backup()
        name = os.path.basename(path)
        db.execute("INSERT INTO sessions (uuid, name) VALUES ('stale', 'Gone')")

        resp = client.post(f"/api/backups/{name}/restore")
        assert resp.status_code == 200 and resp.get_json()["success"] is True
        assert karaoke.restored is True
        # The stale row is gone (restore replaced), and a pre-restore backup exists.
        assert db.query("SELECT COUNT(*) FROM sessions WHERE uuid = 'stale'")[0][0] == 0
        assert _backup_count(manager) == 2

    def test_backup_first_false_skips_the_safety_copy(self, client, manager):
        name = os.path.basename(manager.create_backup())
        resp = client.post(f"/api/backups/{name}/restore", data={"backup_first": "false"})
        assert resp.status_code == 200
        assert _backup_count(manager) == 1

    def test_invalid_name_is_400(self, client):
        resp = client.post("/api/backups/evil.json/restore")
        assert resp.status_code == 400

    def test_newer_schema_is_refused_409(self, client, manager, db):
        path = manager.create_backup()
        # Rewrite the saved dump to claim a newer schema.
        dump = db_backup.load_dump(open(path, encoding="utf-8").read())
        dump["schema_version"] = db.schema_version + 1
        with open(path, "w", encoding="utf-8") as f:
            f.write(db_backup.dump_to_json(dump))
        resp = client.post(f"/api/backups/{os.path.basename(path)}/restore")
        assert resp.status_code == 409


class TestRestoreUpload:
    def test_restores_from_an_uploaded_dump(self, client, db):
        dump = db_backup.build_dump(db)
        upload = (io.BytesIO(db_backup.dump_to_json(dump).encode("utf-8")), "backup.json")
        resp = client.post(
            "/api/backups/restore-upload",
            data={"file": upload, "backup_first": "false"},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 200 and resp.get_json()["success"] is True

    def test_missing_file_is_400(self, client):
        resp = client.post("/api/backups/restore-upload", data={"backup_first": "false"})
        assert resp.status_code == 400

    def test_non_json_is_400(self, client):
        upload = (io.BytesIO(b"not a backup"), "x.json")
        resp = client.post(
            "/api/backups/restore-upload",
            data={"file": upload, "backup_first": "false"},
            content_type="multipart/form-data",
        )
        assert resp.status_code == 400


class TestResetDatabase:
    def test_reset_empties_and_backs_up_first(self, client, karaoke, manager, db):
        resp = client.post("/api/database/reset")
        assert resp.status_code == 200 and resp.get_json()["success"] is True
        assert karaoke.reset_called is True
        assert db.get_song_count() == 0
        assert _backup_count(manager) == 1  # the pre-reset safety copy
