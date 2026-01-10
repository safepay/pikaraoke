# Stage 3: Admin UI - Manage Song Library

**Stage:** 3 of 4
**Status:** Ready for Implementation (After Stage 2)
**Prerequisites:** Stage 2 (Read-Only Integration Complete)
**Estimated Effort:** 1-2 days
**Risk Level:** Medium

## Objective

Expose database management in admin UI:

1. **Synchronize Library** - Manually trigger database sync
2. **Reset Database** - Wipe and rebuild from scratch
3. **Download Backup** - Export database snapshot
4. **Restore from Backup** - Import backup file

**Requirements:** Clear feedback, confirmation dialogs for destructive actions, graceful errors, mobile-responsive.

## Backend Routes

### Route 1: Synchronize Library

```python
from __future__ import annotations

import logging
from datetime import datetime

from flask import current_app, jsonify


@admin_bp.route("/sync_library")
@requires_admin
def sync_library():
    """Manually trigger library synchronization.

    Returns:
        JSON with stats or error message
    """
    try:
        k = current_app.karaoke_instance

        stats = k.db.scan_library(k.download_path)

        k.available_songs.clear()
        k.available_songs.update(k.db.get_all_song_paths())

        k.db.conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_scan', ?)",
            (datetime.now().isoformat(),),
        )
        k.db.conn.commit()

        return jsonify(
            {
                "success": True,
                "message": (
                    f"Library synchronized. {stats['added']} added, "
                    f"{stats['moved']} moved, {stats['deleted']} deleted, "
                    f"{stats['updated']} updated."
                ),
                "stats": stats,
                "total_songs": k.db.get_song_count(),
            }
        )

    except Exception as e:
        logging.error(f"Sync library failed: {e}")
        return (
            jsonify({"success": False, "message": f"Synchronization failed: {e}"}),
            500,
        )
```

### Route 2: Reset Database

```python
from __future__ import annotations

import logging
import os
from datetime import datetime

from flask import current_app, jsonify

from pikaraoke.lib.karaoke_database import KaraokeDatabase


@admin_bp.route("/reset_database")
@requires_admin
def reset_database():
    """Completely wipe and rebuild database.

    Returns:
        JSON with stats or error message
    """
    try:
        k = current_app.karaoke_instance

        k.db.close()

        for ext in ["", "-wal", "-shm"]:
            db_file = k.db.db_path + ext
            if os.path.exists(db_file):
                try:
                    os.remove(db_file)
                    logging.info(f"Deleted {db_file}")
                except OSError as e:
                    logging.warning(f"Failed to delete {db_file}: {e}")

        k.db = KaraokeDatabase()

        stats = k.db.scan_library(k.download_path)

        k.available_songs.clear()
        k.available_songs.update(k.db.get_all_song_paths())

        k.db.conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_scan', ?)",
            (datetime.now().isoformat(),),
        )
        k.db.conn.commit()

        return jsonify(
            {
                "success": True,
                "message": f"Database reset complete. {stats['added']} songs found.",
                "stats": stats,
                "total_songs": k.db.get_song_count(),
            }
        )

    except Exception as e:
        logging.error(f"Reset database failed: {e}")
        try:
            k = current_app.karaoke_instance
            k.db = KaraokeDatabase()
        except Exception:
            pass

        return jsonify({"success": False, "message": f"Reset failed: {e}"}), 500
```

### Route 3: Download Backup

```python
from __future__ import annotations

import logging
import os

from flask import current_app, send_file


@admin_bp.route("/download_backup")
@requires_admin
def download_backup():
    """Generate and download database backup.

    Returns:
        .db file download or error page
    """
    try:
        k = current_app.karaoke_instance

        backup_path = k.db.create_backup_file()

        if not backup_path:
            return "Backup creation failed. Check logs.", 500

        return send_file(
            backup_path,
            as_attachment=True,
            download_name=os.path.basename(backup_path),
            mimetype="application/x-sqlite3",
        )

    except Exception as e:
        logging.error(f"Download backup failed: {e}")
        return f"Backup download failed: {e}", 500
```

### Route 4: Restore Backup

```python
from __future__ import annotations

import logging
import os
import tempfile

from flask import current_app, jsonify, request
from werkzeug.utils import secure_filename


@admin_bp.route("/restore_backup", methods=["POST"])
@requires_admin
def restore_backup():
    """Restore database from uploaded file.

    Expects:
        multipart/form-data with 'backup_file' field

    Returns:
        JSON with success/error message
    """
    try:
        k = current_app.karaoke_instance

        if "backup_file" not in request.files:
            return jsonify({"success": False, "message": "No file uploaded"}), 400

        file = request.files["backup_file"]

        if file.filename == "":
            return jsonify({"success": False, "message": "No file selected"}), 400

        if not file.filename.endswith(".db"):
            return jsonify({"success": False, "message": "Invalid file type"}), 400

        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, secure_filename(file.filename))
        file.save(temp_path)

        success, message = k.db.restore_from_file(temp_path)

        try:
            os.remove(temp_path)
        except Exception:
            pass

        if success:
            k.available_songs.clear()
            k.available_songs.update(k.db.get_all_song_paths())

            return jsonify(
                {
                    "success": True,
                    "message": message,
                    "total_songs": k.db.get_song_count(),
                }
            )
        return jsonify({"success": False, "message": message}), 500

    except Exception as e:
        logging.error(f"Restore backup failed: {e}")
        return jsonify({"success": False, "message": f"Restore failed: {e}"}), 500
```

### Route 5: Get Library Stats

```python
from __future__ import annotations

import logging

from flask import current_app, jsonify


@admin_bp.route("/library_stats")
@requires_admin
def library_stats():
    """Get library statistics.

    Returns:
        JSON with song count and last scan time
    """
    try:
        k = current_app.karaoke_instance

        cursor = k.db.conn.execute("SELECT value FROM metadata WHERE key = 'last_scan'")
        row = cursor.fetchone()
        last_scan = row[0] if row else "Never"

        return jsonify(
            {
                "success": True,
                "total_songs": k.db.get_song_count(),
                "last_scan": last_scan,
            }
        )

    except Exception as e:
        logging.error(f"Get library stats failed: {e}")
        return jsonify({"success": False, "message": str(e)}), 500
```

## Template Updates

**File:** `pikaraoke/templates/info.html`

**Section to Replace:** Lines 408-424 (current "Refresh the song list")

### HTML Structure

Key sections:

1. **Library Status:** Display total songs and last sync time
2. **Synchronize Button:** Trigger manual sync
3. **Reset Button:** Wipe and rebuild with double confirmation
4. **Download Backup Link:** Direct download
5. **Restore Form:** File upload with validation

**Template approach:** Use Bulma CSS cards with collapsible sections. Status indicators update via AJAX.

### JavaScript Requirements

**Core functionality:**

1. **Load stats on page load** - AJAX GET to `/library_stats`
2. **Sync handler** - Button click → loading state → update stats
3. **Reset handler** - Double confirmation → loading state → reload page
4. **File upload** - Display filename → enable restore button
5. **Restore handler** - Form submit → AJAX POST → reload page

**Implementation pattern:**

```javascript
$(function () {
    // Load stats
    $.get("/admin/library_stats").done(function (data) {
        $("#total-songs-count").text(data.total_songs.toLocaleString());
        $("#last-sync-time").text(
            data.last_scan !== "Never" ? new Date(data.last_scan).toLocaleString() : "Never"
        );
    });

    // Sync button
    $("#sync-library-btn").click(function (e) {
        e.preventDefault();
        const $btn = $(this);
        const $result = $("#sync-result");

        $btn.prop("disabled", true).addClass("is-loading");
        $result.removeClass("is-success is-danger").addClass("is-hidden");

        $.get("/admin/sync_library")
            .done(function (data) {
                if (data.success) {
                    $result
                        .removeClass("is-hidden is-danger")
                        .addClass("is-success")
                        .html(
                            `<strong>Success!</strong><br>${data.message}<br>` +
                                `<small>Total songs: ${data.total_songs.toLocaleString()}</small>`
                        );
                    loadLibraryStats();
                } else {
                    $result
                        .removeClass("is-hidden is-success")
                        .addClass("is-danger")
                        .text(data.message);
                }
            })
            .fail(function (xhr) {
                $result
                    .removeClass("is-hidden is-success")
                    .addClass("is-danger")
                    .text(xhr.responseJSON?.message || "Synchronization failed");
            })
            .always(function () {
                $btn.prop("disabled", false).removeClass("is-loading");
            });
    });

    // Reset button (double confirmation)
    $("#reset-database-btn").click(function (e) {
        e.preventDefault();

        if (
            !confirm(
                "Are you sure? This will DELETE ALL metadata. Consider downloading a backup first."
            )
        ) {
            return;
        }

        if (!confirm("Final confirmation: Reset database and lose all metadata?")) {
            return;
        }

        const $btn = $(this);
        const $result = $("#reset-result");

        $btn.prop("disabled", true).addClass("is-loading");

        $.get("/admin/reset_database")
            .done(function (data) {
                if (data.success) {
                    $result
                        .removeClass("is-hidden is-danger")
                        .addClass("is-success")
                        .html(
                            `<strong>Success!</strong><br>${data.message}<br>` +
                                `<em>Refreshing page in 3 seconds...</em>`
                        );
                    setTimeout(() => location.reload(), 3000);
                } else {
                    $result
                        .removeClass("is-hidden is-success")
                        .addClass("is-danger")
                        .text(data.message);
                }
            })
            .fail(function (xhr) {
                $result
                    .removeClass("is-hidden is-success")
                    .addClass("is-danger")
                    .text(xhr.responseJSON?.message || "Reset failed");
            })
            .always(function () {
                $btn.prop("disabled", false).removeClass("is-loading");
            });
    });

    // File upload: show filename
    $("#backup-file-input").change(function () {
        const file = this.files[0];
        if (file) {
            $("#backup-file-name").text(file.name);
            $("#restore-btn").prop("disabled", false);
        } else {
            $("#backup-file-name").text("No file selected");
            $("#restore-btn").prop("disabled", true);
        }
    });

    // Restore form submit
    $("#restore-form").submit(function (e) {
        e.preventDefault();

        if (!confirm("Are you sure? This will overwrite your current library.")) {
            return;
        }

        const formData = new FormData(this);
        const $btn = $("#restore-btn");
        const $result = $("#restore-result");

        $btn.prop("disabled", true).addClass("is-loading");

        $.ajax({
            url: "/admin/restore_backup",
            type: "POST",
            data: formData,
            processData: false,
            contentType: false,
            success: function (data) {
                if (data.success) {
                    $result
                        .removeClass("is-hidden is-danger")
                        .addClass("is-success")
                        .html(
                            `<strong>Success!</strong><br>${data.message}<br>` +
                                `<em>Refreshing in 3 seconds...</em>`
                        );
                    setTimeout(() => location.reload(), 3000);
                } else {
                    $result
                        .removeClass("is-hidden is-success")
                        .addClass("is-danger")
                        .text(data.message);
                }
            },
            error: function (xhr) {
                $result
                    .removeClass("is-hidden is-success")
                    .addClass("is-danger")
                    .text(xhr.responseJSON?.message || "Restore failed");
            },
            complete: function () {
                $btn.prop("disabled", false).removeClass("is-loading");
            },
        });
    });
});
```

## Security Considerations

### Admin Authentication

```python
from __future__ import annotations

from functools import wraps

from flask import redirect, request, session, url_for


def requires_admin(f):
    """Decorator to require admin authentication."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin.login", next=request.url))
        return f(*args, **kwargs)

    return decorated_function
```

### File Upload Validation

```python
# In restore_backup route

# 1. Extension validation
if not file.filename.endswith(".db"):
    return jsonify({"success": False, "message": "Invalid file type"}), 400

# 2. Size limit (100 MB max)
MAX_FILE_SIZE = 100 * 1024 * 1024
file.seek(0, os.SEEK_END)
file_size = file.tell()
file.seek(0)

if file_size > MAX_FILE_SIZE:
    return jsonify({"success": False, "message": "File too large"}), 400

# 3. SQLite format validation (in KaraokeDatabase.restore_from_file)
with open(uploaded_file_path, "rb") as f:
    header = f.read(16)
if b"SQLite format 3" not in header:
    return False, "Invalid file format"
```

### Path Traversal Prevention

```python
from werkzeug.utils import secure_filename

temp_path = os.path.join(temp_dir, secure_filename(file.filename))
```

## Testing Checklist

### Manual Tests

1. **Synchronize:** No changes → 0 added/moved/deleted
2. **Synchronize:** Add file → 1 added
3. **Synchronize:** Move file → 1 moved, 0 deleted
4. **Reset:** Double confirmation works, database wiped
5. **Download Backup:** File downloads and is valid SQLite
6. **Restore:** Upload backup → success → songs match
7. **Error Handling:** Invalid file → error message
8. **Mobile:** UI works on phone/tablet

### Error Scenarios

- Upload non-SQLite file → error
- Upload corrupted .db → error
- Upload incompatible schema → error
- Sync while disk full → graceful error
- Reset while locked → graceful error

## Success Criteria

- All four features work correctly
- No data loss
- Error handling graceful
- User feedback clear
- Mobile-friendly UI
- All routes authenticated
- File uploads validated
- No XSS vulnerabilities

## Rollback Plan

**Option 1:** Disable features (comment out routes, hide UI)

**Option 2:** Revert template (restore old "Refresh Song List" UI)

**Option 3:** Full rollback to Stage 2 (auto-sync only)

## Next Steps

After Stage 3 completion:

1. All manual tests pass
2. Security audit passed
3. Documentation published
4. (Optional) Proceed to Stage 4 (Metadata Enrichment)

**Stage 3 Completion:** Database migration is feature-complete and production-ready. Stage 4 is enhancement, not requirement.

**Document Status:** Complete
**Last Updated:** 2026-01-11
