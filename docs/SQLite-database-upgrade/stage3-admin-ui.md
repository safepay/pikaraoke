# Stage 3: Admin UI - Manage Song Library - Complete Implementation Plan

**Stage:** 3 of 4
**Status:** 📋 Ready for Implementation (After Stage 2)
**Prerequisites:** Stage 2 (Read-Only Integration Complete)
**Estimated Effort:** 1-2 days
**Risk Level:** Medium

______________________________________________________________________

## Objective

Expose database management features through the admin web interface, allowing users to:

1. **Synchronize Library** - Manually trigger database sync with disk
2. **Download Backup** - Export database snapshot for safekeeping
3. **Restore from Backup** - Import previously exported database

**Critical Requirements:**

- Clear user feedback on all operations
- Confirmation dialogs for destructive actions
- Graceful error handling with user-friendly messages
- Mobile-responsive UI (Bulma CSS framework)

______________________________________________________________________

## UI Design

### Current State (Stage 2)

**Location:** `pikaraoke/templates/info.html:410-424`

**Section Title:** "Refresh the song list"

**Current UI:**

```
┌─────────────────────────────────────────┐
│ ▼ Refresh the song list                │
├─────────────────────────────────────────┤
│ You should only need to do this if you │
│ manually copied files to the download  │
│ directory while pikaraoke was running.  │
│                                         │
│ [Rescan song directory]                │
└─────────────────────────────────────────┘
```

### Proposed State (Stage 3)

**Section Title:** "Manage Song Library" *(more comprehensive)*

**New UI:**

```
┌───────────────────────────────────────────────────────┐
│ ▼ Manage Song Library                                │
├───────────────────────────────────────────────────────┤
│                                                       │
│ 📊 Library Status                                    │
│ ─────────────────────────────────────────────────     │
│ Total songs: 1,247                                   │
│ Last synchronized: 2026-01-09 14:30:22               │
│                                                       │
│ 🔄 Synchronize Library                               │
│ ─────────────────────────────────────────────────     │
│ Scan for new, moved, or deleted files on disk.       │
│ [Synchronize Library]                                │
│                                                       │
│ 💾 Backup & Restore                                  │
│ ─────────────────────────────────────────────────     │
│ Download a snapshot of your song database for        │
│ safekeeping or transfer to another system.           │
│ [Download Database Backup]                           │
│                                                       │
│ Restore from a previously downloaded backup:         │
│ [Choose File...] [Restore from Backup]               │
│ ⚠ Warning: This will overwrite your current library. │
│                                                       │
└───────────────────────────────────────────────────────┘
```

______________________________________________________________________

## Implementation Files

### File 1: Backend Routes

**Assumption:** Admin routes are in a Flask blueprint (typical pattern for PiKaraoke)

Create or modify the admin routes file to add these endpoints:

#### Route 1: Synchronize Library

```python
@admin_bp.route("/sync_library")
@requires_admin
def sync_library():
    """Manually trigger library synchronization.

    Returns JSON with stats or error message.
    """
    try:
        from flask import current_app

        k = current_app.karaoke_instance  # Access to Karaoke instance

        # Trigger database sync
        stats = k.db.scan_library(k.download_path)

        # Update legacy SongList for backwards compatibility
        k.available_songs.clear()
        k.available_songs.update(k.db.get_all_song_paths())

        # Update last scan timestamp in metadata
        from datetime import datetime

        k.db.conn.execute(
            "INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_scan', ?)",
            (datetime.now().isoformat(),),
        )
        k.db.conn.commit()

        # Return success with stats
        return jsonify(
            {
                "success": True,
                "message": f"Library synchronized. {stats['added']} added, {stats['moved']} moved, "
                f"{stats['deleted']} deleted, {stats['updated']} updated.",
                "stats": stats,
                "total_songs": k.db.get_song_count(),
            }
        )

    except Exception as e:
        logging.error(f"Sync library failed: {e}")
        return (
            jsonify({"success": False, "message": f"Synchronization failed: {str(e)}"}),
            500,
        )
```

#### Route 2: Download Backup

```python
from flask import send_file
import os


@admin_bp.route("/download_backup")
@requires_admin
def download_backup():
    """Generate and download database backup.

    Returns .db file download or error page.
    """
    try:
        from flask import current_app

        k = current_app.karaoke_instance

        # Create backup
        backup_path = k.db.create_backup_file()

        if not backup_path:
            return "Backup creation failed. Check logs.", 500

        # Send file to user
        return send_file(
            backup_path,
            as_attachment=True,
            download_name=os.path.basename(backup_path),
            mimetype="application/x-sqlite3",
        )

    except Exception as e:
        logging.error(f"Download backup failed: {e}")
        return f"Backup download failed: {str(e)}", 500
```

#### Route 3: Upload and Restore Backup

```python
from flask import request
from werkzeug.utils import secure_filename
import tempfile


@admin_bp.route("/restore_backup", methods=["POST"])
@requires_admin
def restore_backup():
    """Restore database from uploaded backup file.

    Expects multipart/form-data with 'backup_file' field.
    Returns JSON with success/error message.
    """
    try:
        from flask import current_app

        k = current_app.karaoke_instance

        # Validate file upload
        if "backup_file" not in request.files:
            return jsonify({"success": False, "message": "No file uploaded"}), 400

        file = request.files["backup_file"]

        if file.filename == "":
            return jsonify({"success": False, "message": "No file selected"}), 400

        # Validate file extension
        if not file.filename.endswith(".db"):
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Invalid file type. Must be a .db file",
                    }
                ),
                400,
            )

        # Save uploaded file to temporary location
        temp_dir = tempfile.gettempdir()
        temp_path = os.path.join(temp_dir, secure_filename(file.filename))
        file.save(temp_path)

        # Attempt restore
        success, message = k.db.restore_from_file(temp_path)

        # Clean up temp file
        try:
            os.remove(temp_path)
        except:
            pass

        if success:
            # Update SongList from restored database
            k.available_songs.clear()
            k.available_songs.update(k.db.get_all_song_paths())

            return jsonify(
                {
                    "success": True,
                    "message": message,
                    "total_songs": k.db.get_song_count(),
                }
            )
        else:
            return jsonify({"success": False, "message": message}), 500

    except Exception as e:
        logging.error(f"Restore backup failed: {e}")
        return jsonify({"success": False, "message": f"Restore failed: {str(e)}"}), 500
```

#### Route 4: Get Library Stats (AJAX)

```python
@admin_bp.route("/library_stats")
@requires_admin
def library_stats():
    """Get current library statistics for UI display.

    Returns JSON with song count and last scan time.
    """
    try:
        from flask import current_app

        k = current_app.karaoke_instance

        # Get last scan time from metadata
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

______________________________________________________________________

### File 2: Template Updates

**File:** `pikaraoke/templates/info.html`

**Section to Replace:** Lines 408-424 (current "Refresh the song list")

**New HTML:**

```html
{# MSG: Title of the library management section. #}
<h1>{% trans %}Library Management{% endtrans %}</h1>

<div class="card">
    <header class="card-header py-3 px-5 collapsible-header is-collapsed">
        {# MSG: Header for the Manage Song Library section #}
        <h3 class="title mb-0">📚 {% trans %}Manage Song Library{% endtrans %}</h3>
    </header>
    <div class="card-content collapsible-content">
        <div class="content">

            {# Library Status #}
            <h5>📊 {% trans %}Library Status{% endtrans %}</h5>
            <div id="library-status" class="box has-background-light">
                <p>
                    <strong>{% trans %}Total songs:{% endtrans %}</strong>
                    <span id="total-songs-count">{{ total_songs }}</span>
                </p>
                <p>
                    <strong>{% trans %}Last synchronized:{% endtrans %}</strong>
                    <span id="last-sync-time">{{ last_scan }}</span>
                </p>
            </div>

            <hr>

            {# Synchronize Library #}
            <h5>🔄 {% trans %}Synchronize Library{% endtrans %}</h5>
            <p class="subtitle is-size-6">
                {# MSG: Explanation of what synchronize does #}
                {% trans -%}
                    Scan your download directory to detect new, moved, or deleted song files.
                    This updates the database to match what's actually on disk.
                {%- endtrans %}
            </p>
            <button id="sync-library-btn" class="button is-primary is-inverted">
                <span class="icon">
                    <i class="fas fa-sync-alt"></i>
                </span>
                <span>{% trans %}Synchronize Library{% endtrans %}</span>
            </button>
            <div id="sync-result" class="notification is-hidden mt-3"></div>

            <hr>

            {# Backup & Restore #}
            <h5>💾 {% trans %}Backup & Restore{% endtrans %}</h5>

            {# Download Backup #}
            <div class="mb-4">
                <p class="subtitle is-size-6">
                    {# MSG: Explanation of backup download #}
                    {% trans -%}
                        Download a snapshot of your song database for safekeeping or
                        transfer to another PiKaraoke installation.
                    {%- endtrans %}
                </p>
                <a href="{{ url_for('admin.download_backup') }}"
                   class="button is-info is-inverted"
                   download>
                    <span class="icon">
                        <i class="fas fa-download"></i>
                    </span>
                    <span>{% trans %}Download Database Backup{% endtrans %}</span>
                </a>
            </div>

            {# Restore from Backup #}
            <div>
                <p class="subtitle is-size-6">
                    {# MSG: Explanation of backup restore #}
                    {% trans -%}
                        Restore your song library from a previously downloaded backup file.
                    {%- endtrans %}
                </p>
                <form id="restore-form" enctype="multipart/form-data">
                    <div class="field has-addons">
                        <div class="control">
                            <div class="file has-name">
                                <label class="file-label">
                                    <input class="file-input" type="file"
                                           id="backup-file-input"
                                           name="backup_file"
                                           accept=".db">
                                    <span class="file-cta">
                                        <span class="file-icon">
                                            <i class="fas fa-upload"></i>
                                        </span>
                                        <span class="file-label">
                                            {% trans %}Choose file...{% endtrans %}
                                        </span>
                                    </span>
                                    <span class="file-name" id="backup-file-name">
                                        {% trans %}No file selected{% endtrans %}
                                    </span>
                                </label>
                            </div>
                        </div>
                        <div class="control">
                            <button type="submit" id="restore-btn"
                                    class="button is-warning"
                                    disabled>
                                <span class="icon">
                                    <i class="fas fa-undo"></i>
                                </span>
                                <span>{% trans %}Restore from Backup{% endtrans %}</span>
                            </button>
                        </div>
                    </div>
                </form>
                <div id="restore-result" class="notification is-hidden mt-3"></div>

                <p class="has-text-warning is-size-7 mt-3">
                    <span class="icon-text">
                        <span class="icon">
                            <i class="fas fa-exclamation-triangle"></i>
                        </span>
                        <span>
                            {# MSG: Warning about restore overwriting data #}
                            {% trans -%}
                                Warning: Restoring will overwrite your current song library.
                                Make sure to download a backup first if you want to keep your current data.
                            {%- endtrans %}
                        </span>
                    </span>
                </p>
            </div>

        </div>
    </div>
</div>
```

**JavaScript to Add (in `{% block scripts %}` section):**

```javascript
$(function() {
    // ============================================================
    // LIBRARY STATUS - Load on page load
    // ============================================================
    function loadLibraryStats() {
        $.get("{{ url_for('admin.library_stats') }}")
            .done(function(data) {
                if (data.success) {
                    $('#total-songs-count').text(data.total_songs.toLocaleString());

                    // Format timestamp nicely
                    let lastScan = data.last_scan;
                    if (lastScan !== 'Never') {
                        const date = new Date(lastScan);
                        lastScan = date.toLocaleString();
                    }
                    $('#last-sync-time').text(lastScan);
                }
            });
    }

    // Load stats on page load
    loadLibraryStats();

    // ============================================================
    // SYNCHRONIZE LIBRARY
    // ============================================================
    $('#sync-library-btn').click(function(e) {
        e.preventDefault();

        const $btn = $(this);
        const $result = $('#sync-result');

        // Disable button and show loading state
        $btn.prop('disabled', true).addClass('is-loading');
        $result.removeClass('is-success is-danger').addClass('is-hidden');

        $.get("{{ url_for('admin.sync_library') }}")
            .done(function(data) {
                if (data.success) {
                    // Show success message with stats
                    $result.removeClass('is-hidden is-danger')
                           .addClass('is-success')
                           .html(`
                               <strong>{% trans %}Success!{% endtrans %}</strong><br>
                               ${data.message}<br>
                               <small>{% trans %}Total songs:{% endtrans %} ${data.total_songs.toLocaleString()}</small>
                           `);

                    // Update stats display
                    loadLibraryStats();
                } else {
                    // Show error
                    $result.removeClass('is-hidden is-success')
                           .addClass('is-danger')
                           .text(data.message);
                }
            })
            .fail(function(xhr) {
                let message = "{% trans %}Synchronization failed. Check logs.{% endtrans %}";
                if (xhr.responseJSON && xhr.responseJSON.message) {
                    message = xhr.responseJSON.message;
                }
                $result.removeClass('is-hidden is-success')
                       .addClass('is-danger')
                       .text(message);
            })
            .always(function() {
                // Re-enable button
                $btn.prop('disabled', false).removeClass('is-loading');
            });
    });

    // ============================================================
    // BACKUP FILE UPLOAD - Show filename when selected
    // ============================================================
    $('#backup-file-input').change(function() {
        const file = this.files[0];
        if (file) {
            $('#backup-file-name').text(file.name);
            $('#restore-btn').prop('disabled', false);
        } else {
            $('#backup-file-name').text("{% trans %}No file selected{% endtrans %}");
            $('#restore-btn').prop('disabled', true);
        }
    });

    // ============================================================
    // RESTORE FROM BACKUP
    // ============================================================
    $('#restore-form').submit(function(e) {
        e.preventDefault();

        // Confirmation dialog
        if (!confirm("{% trans %}Are you sure you want to restore from this backup? This will overwrite your current library.{% endtrans %}")) {
            return;
        }

        const $form = $(this);
        const $btn = $('#restore-btn');
        const $result = $('#restore-result');
        const formData = new FormData(this);

        // Disable button and show loading
        $btn.prop('disabled', true).addClass('is-loading');
        $result.removeClass('is-success is-danger').addClass('is-hidden');

        $.ajax({
            url: "{{ url_for('admin.restore_backup') }}",
            type: 'POST',
            data: formData,
            processData: false,
            contentType: false,
            success: function(data) {
                if (data.success) {
                    $result.removeClass('is-hidden is-danger')
                           .addClass('is-success')
                           .html(`
                               <strong>{% trans %}Success!{% endtrans %}</strong><br>
                               ${data.message}<br>
                               <small>{% trans %}Total songs:{% endtrans %} ${data.total_songs.toLocaleString()}</small><br>
                               <em>{% trans %}Refreshing page in 3 seconds...{% endtrans %}</em>
                           `);

                    // Reload stats and page after success
                    setTimeout(function() {
                        location.reload();
                    }, 3000);
                } else {
                    $result.removeClass('is-hidden is-success')
                           .addClass('is-danger')
                           .text(data.message);
                }
            },
            error: function(xhr) {
                let message = "{% trans %}Restore failed. Check logs.{% endtrans %}";
                if (xhr.responseJSON && xhr.responseJSON.message) {
                    message = xhr.responseJSON.message;
                }
                $result.removeClass('is-hidden is-success')
                       .addClass('is-danger')
                       .text(message);
            },
            complete: function() {
                $btn.prop('disabled', false).removeClass('is-loading');
            }
        });
    });
});
```

______________________________________________________________________

## Security Considerations

### 1. Admin Authentication

**Requirement:** All routes MUST require admin authentication.

```python
from functools import wraps
from flask import session, redirect, url_for, request


def requires_admin(f):
    """Decorator to require admin authentication."""

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin.login", next=request.url))
        return f(*args, **kwargs)

    return decorated_function
```

### 2. File Upload Validation

```python
# In restore_backup route

# 1. File extension validation
if not file.filename.endswith(".db"):
    return jsonify({"success": False, "message": "Invalid file type"}), 400

# 2. File size limit (e.g., 100 MB max)
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB
file.seek(0, os.SEEK_END)
file_size = file.tell()
file.seek(0)

if file_size > MAX_FILE_SIZE:
    return jsonify({"success": False, "message": "File too large"}), 400

# 3. SQLite format validation (in KaraokeDatabase.restore_from_file)
```

### 3. Path Traversal Prevention

```python
from werkzeug.utils import secure_filename

# In restore_backup route
temp_path = os.path.join(temp_dir, secure_filename(file.filename))
```

### 4. CSRF Protection

If using Flask-WTF:

```html
<form id="restore-form" enctype="multipart/form-data">
    {{ csrf_token() }}
    <!-- ... -->
</form>
```

______________________________________________________________________

## Testing Checklist

### Manual Testing

#### Test 1: Synchronize Library

- \[ \] Click "Synchronize Library" with no changes → Shows "0 added, 0 moved, 0 deleted"
- \[ \] Add new file to disk, click sync → Shows "1 added"
- \[ \] Move file on disk, click sync → Shows "1 moved, 0 deleted"
- \[ \] Delete file from disk, click sync → Shows "1 deleted"
- \[ \] Stats update correctly after sync
- \[ \] Last sync timestamp updates
- \[ \] Success notification displays

#### Test 2: Download Backup

- \[ \] Click "Download Database Backup" → File downloads
- \[ \] Downloaded file is valid SQLite (can open in DB Browser)
- \[ \] Downloaded file contains all songs
- \[ \] Filename includes timestamp
- \[ \] File size is reasonable (not corrupt/empty)

#### Test 3: Restore from Backup

- \[ \] Select backup file → Filename displays, button enables
- \[ \] Click "Restore" → Confirmation dialog appears
- \[ \] Cancel confirmation → Operation aborted
- \[ \] Confirm restoration → Success message shows
- \[ \] Page refreshes after 3 seconds
- \[ \] Songs match backup content
- \[ \] Stats update correctly

#### Test 4: Error Handling

- \[ \] Upload non-SQLite file → Error message shown
- \[ \] Upload corrupted .db file → Error message shown
- \[ \] Upload incompatible schema version → Error message shown
- \[ \] Trigger sync while disk is full → Graceful error
- \[ \] Trigger backup while disk is full → Graceful error

#### Test 5: Mobile Responsiveness

- \[ \] UI works on phone (\< 480px width)
- \[ \] UI works on tablet (481-768px width)
- \[ \] Buttons are tappable (not too small)
- \[ \] File upload works on mobile
- \[ \] Collapsible sections work correctly

#### Test 6: Security

- \[ \] All routes require admin login
- \[ \] Non-admin redirected to login page
- \[ \] CSRF token validation works (if enabled)
- \[ \] Path traversal attack prevented
- \[ \] File size limit enforced

______________________________________________________________________

## Success Criteria

### Functional

- \[ \] All three features work correctly
- \[ \] No data loss incidents
- \[ \] Error handling is graceful
- \[ \] User feedback is clear and actionable

### UX/UI

- \[ \] UI is intuitive (no documentation needed)
- \[ \] Mobile-friendly
- \[ \] Consistent with existing design
- \[ \] Loading states are clear

### Performance

- \[ \] Sync completes in \< 30s for 1K songs
- \[ \] Backup download starts immediately
- \[ \] Restore completes in \< 5s
- \[ \] No memory leaks

### Security

- \[ \] All routes properly authenticated
- \[ \] File uploads validated
- \[ \] CSRF protection active
- \[ \] No XSS vulnerabilities

______________________________________________________________________

## Rollback Plan

If critical issues discovered:

**Option 1: Disable Features**

- Comment out new routes
- Hide UI elements
- Database still works in read-only mode (Stage 2)

**Option 2: Revert Template**

- Restore old "Refresh Song List" UI
- Remove JavaScript code
- Remove new routes

**Option 3: Full Rollback to Stage 2**

- Revert all changes
- Return to auto-sync-on-startup only

______________________________________________________________________

## Next Steps

After Stage 3 completion:

1. ✅ All manual tests pass
2. ✅ User acceptance testing complete
3. ✅ Security audit passed
4. ✅ Documentation published
5. 📝 (Optional) Proceed to Stage 4 (Metadata Enrichment)

**Stage 3 Completion:** At this point, the database migration is **feature-complete** and production-ready. Stage 4 is an enhancement, not a requirement.

______________________________________________________________________

## File Checklist

### Files to Create/Modify

**Backend:**

- \[ \] Admin routes file - Add 4 new routes (sync, download, upload, stats)
- \[ \] Ensure `@requires_admin` decorator exists

**Frontend:**

- \[ \] `pikaraoke/templates/info.html` - Replace "Refresh" section
- \[ \] Add JavaScript in `{% block scripts %}` section

**Template Variables:**

- \[ \] Ensure `total_songs` is passed to template
- \[ \] Ensure `last_scan` is passed to template

______________________________________________________________________

**Document Status:** ✅ Complete
**Last Updated:** 2026-01-09
**Ready for:** Implementation after Stage 2
