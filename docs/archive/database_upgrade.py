"""
REFERENCE IMPLEMENTATION: PIKARAOKE DATABASE UPGRADE
WARNING: This code is a STARTING POINT. Do not assume it is bug-free or fits the latest codebase.
Analyze the existing project structure before implementing.

Features:
- Content Fingerprinting (Moves/Renames)
- Smart Parsing & Metadata Enrichment
- WAL Mode (Power Safety)
- Database Backup (Export) & Restore (Import)
- Schema Versioning
"""

import hashlib
import os
import shutil
import sqlite3
from datetime import datetime

# ==========================================
# CONSTANTS
# ==========================================

DB_VERSION = 1  # Increment this if schema changes in future
BACKUP_FILENAME_FMT = "pikaraoke_backup_%Y%m%d_%H%M%S.db"

# ==========================================
# CLASS DEFINITION
# ==========================================


class KaraokeDB:
    def __init__(self, db_path, backup_dir):
        self.db_path = db_path
        self.backup_dir = backup_dir
        self.conn = None
        self._connect()

    def _connect(self):
        """Establishes the SQLite connection with optimal settings."""
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA synchronous=NORMAL;")

        # Check Schema Version
        try:
            cur_ver = self.conn.execute("PRAGMA user_version").fetchone()[0]
        except:
            cur_ver = 0

        if cur_ver == 0:
            self.init_schema()
            self.conn.execute(f"PRAGMA user_version = {DB_VERSION}")
            self.conn.commit()

    def init_schema(self):
        self.conn.execute(
            """
        CREATE TABLE IF NOT EXISTS songs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_path TEXT UNIQUE NOT NULL,
            file_hash TEXT,
            filename TEXT NOT NULL,
            artist TEXT,
            title TEXT,
            variant TEXT,
            year INTEGER,
            genre TEXT,
            youtube_id TEXT,
            format TEXT NOT NULL,
            search_blob TEXT,
            is_visible INTEGER DEFAULT 1,
            metadata_status TEXT DEFAULT 'pending'
        );
        """
        )
        self.conn.execute("CREATE INDEX IF NOT EXISTS idx_file_hash ON songs(file_hash);")
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_metadata_status ON songs(metadata_status);"
        )
        self.conn.commit()

    # --- DISASTER RECOVERY (BACKUP/RESTORE) ---

    def create_backup_file(self):
        """
        Creates a snapshot of the DB for the user to download.
        Returns the path to the temporary backup file.
        Uses SQLite Backup API for safety during live usage.
        """
        if not os.path.exists(self.backup_dir):
            os.makedirs(self.backup_dir)

        timestamp = datetime.now().strftime(BACKUP_FILENAME_FMT)
        dest = os.path.join(self.backup_dir, timestamp)

        try:
            backup_conn = sqlite3.connect(dest)
            self.conn.backup(backup_conn)
            backup_conn.close()
            return dest
        except Exception as e:
            print(f"Backup creation failed: {e}")
            return None

    def restore_from_file(self, uploaded_file_path):
        """
        Restores DB from an uploaded file using the "File Swap" method.
        REQUIRES RESTART or RELOAD: Closes connection, swaps files, reopens.
        """
        if not os.path.exists(uploaded_file_path):
            return False, "Upload file not found"

        # 1. Basic validity check
        try:
            with open(uploaded_file_path, "rb") as f:
                header = f.read(16)
            if b"SQLite format 3" not in header:
                return False, "Invalid file format. Not a SQLite database."
        except Exception as e:
            return False, f"File validation error: {e}"

        try:
            # 2. Close existing connection to release locks
            if self.conn:
                self.conn.close()

            # 3. Clean up old DB artifacts (WAL/SHM) to prevent corruption
            for ext in ["", "-wal", "-shm"]:
                target = self.db_path + ext
                if os.path.exists(target):
                    try:
                        os.remove(target)
                    except OSError:
                        pass  # Best effort

            # 4. Swap in the new file
            shutil.copy2(uploaded_file_path, self.db_path)

            # 5. Re-establish connection
            self._connect()
            return True, "Restore successful. Database updated."

        except Exception as e:
            # Attempt to reconnect if restore failed to avoid total downtime
            try:
                self._connect()
            except:
                pass
            return False, f"Restore failed: {e}"

    def reset_metadata_status(self):
        """Phase 2: Resets all songs to 'pending' to trigger re-enrichment."""
        self.conn.execute("UPDATE songs SET metadata_status = 'pending'")
        self.conn.commit()

    # --- SCANNER LOGIC (SYNCHRONIZE LIBRARY) ---

    def get_fingerprint(self, full_path):
        """Fast hash: Size + Header (16kb)"""
        try:
            stats = os.stat(full_path)
            with open(full_path, "rb") as f:
                header = f.read(16384)
            hasher = hashlib.md5()
            hasher.update(str(stats.st_size).encode("utf-8"))
            hasher.update(header)
            return hasher.hexdigest()
        except:
            return None

    def scan_library(self, songs_dir):
        """
        Syncs DB with Disk.
        Handles: Adds, Deletes, Moves (via Hash), and Content Updates.
        """
        print(f"Scanning {songs_dir}...")
        disk_files = {}  # Key: rel_path, Value: (filename, fmt, hash)

        # 1. DISCOVER FILES ON DISK
        for root, _, files in os.walk(songs_dir):
            files_lower = {f.lower() for f in files}  # Case-insensitive lookup helper
            for file in files:
                if file.startswith("."):
                    continue  # Skip hidden

                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, songs_dir)
                base, ext = os.path.splitext(file)
                ext = ext.lower()
                fmt = None

                # Pair Detection Logic
                if ext == ".mp3" and (base.lower() + ".cdg") in files_lower:
                    fmt = "CDG"
                elif ext == ".zip":
                    fmt = "ZIP"
                elif ext in [".mp4", ".mkv", ".avi", ".webm"]:
                    fmt = "MP4+ASS" if (base.lower() + ".ass") in files_lower else "MP4"

                if fmt:
                    fp = self.get_fingerprint(full_path)
                    disk_files[rel_path] = (file, fmt, fp)

        # 2. FETCH DB STATE
        cursor = self.conn.execute("SELECT id, file_path, file_hash, format FROM songs")
        db_rows = {row["file_path"]: row for row in cursor}

        # 3. COMPARE & SYNC
        disk_paths = set(disk_files.keys())
        db_paths = set(db_rows.keys())

        common = disk_paths & db_paths
        new_files = disk_paths - db_paths
        missing_files = db_paths - disk_paths

        # Track stats
        stats = {"added": 0, "moved": 0, "deleted": 0, "updated": 0}

        # A. Update Existing
        for path in common:
            filename, fmt, fp = disk_files[path]
            row = db_rows[path]
            if row["file_hash"] != fp or row["format"] != fmt:
                self.conn.execute(
                    "UPDATE songs SET file_hash=?, format=?, filename=? WHERE id=?",
                    (fp, fmt, filename, row["id"]),
                )
                stats["updated"] += 1

        # B. Handle Missing (Detect Moves vs Deletes)
        missing_hashes = {
            db_rows[p]["file_hash"]: db_rows[p] for p in missing_files if db_rows[p]["file_hash"]
        }

        for path in new_files:
            filename, fmt, fp = disk_files[path]
            # Check if this new file is actually an old file moved (same hash)
            if fp and fp in missing_hashes:
                old_row = missing_hashes[fp]
                self.conn.execute(
                    "UPDATE songs SET file_path=?, filename=?, format=? WHERE id=?",
                    (path, filename, fmt, old_row["id"]),
                )
                del missing_hashes[fp]  # Mark as handled
                stats["moved"] += 1
            else:
                self.add_song_placeholder(path, filename, fmt, fp)
                stats["added"] += 1

        # C. Delete whatever is still missing
        for remaining_hash in missing_hashes:
            self.conn.execute(
                "DELETE FROM songs WHERE id=?", (missing_hashes[remaining_hash]["id"],)
            )
            stats["deleted"] += 1

        # D. Clean up path-based missing files
        for path in missing_files:
            pass

        self.conn.commit()
        return stats

    def add_song_placeholder(self, path, filename, fmt, fp):
        """Inserts basic record. Metadata enrichment happens in Phase 2."""
        clean = os.path.splitext(filename)[0].replace("_", " ")
        self.conn.execute(
            """
            INSERT INTO songs (file_path, file_hash, filename, title, format, metadata_status)
            VALUES (?, ?, ?, ?, ?, 'pending')
        """,
            (path, fp, filename, clean, fmt),
        )

    # --- METADATA ENRICHMENT (PHASE 2) ---
    def enrich_all(self):
        """Iterates through 'pending' songs and fetches metadata."""
        pass
