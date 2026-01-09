# Development Database Tooling

**Purpose:** Provide developers with direct database access during SQLite implementation (Stages 1-4)

**Status:** Planned for Stage 1 implementation

______________________________________________________________________

## Overview

During development of the SQLite database migration, developers need tools to:

- Inspect database schema and indexes
- Execute SQL queries for testing
- Browse table contents during development
- Debug data integrity issues
- Monitor database performance

This document describes the lightweight development-only database viewer integrated into PiKaraoke.

______________________________________________________________________

## Solution: sqlite-web

**Tool:** [sqlite-web](https://github.com/coleifer/sqlite-web)

**Advantages:**

- Pure Python, Flask-based (matches existing stack)
- Minimal dependencies
- Web-based interface (consistent with PiKaraoke UI)
- Read-only mode available for safety
- Very lightweight (~200KB)
- Conditionally loaded only when development flag is set

______________________________________________________________________

## Installation

```bash
# Add as development dependency
uv add --dev sqlite-web
```

This will update `pyproject.toml`:

```toml
[project.optional-dependencies]
dev = [
  "pre-commit>=3.7.1",
  "pytest>=9.0.2",
  "pytest-cov>=7.0.0",
  "sqlite-web>=0.5.0",  # Added for database development
]
```

______________________________________________________________________

## Usage

### Starting PiKaraoke with Development Mode

```bash
# Enable development mode with the --dev-mode flag
python -m pikaraoke --dev-mode

# Or with other options
python -m pikaraoke --dev-mode --port 5555 --download-path /path/to/songs
```

### Accessing the Database Viewer

Once running with `--dev-mode`:

1. Open your web browser
2. Navigate to: `http://localhost:5555/dev/database`
3. Authenticate with admin credentials (reuses existing `@is_admin` decorator)

______________________________________________________________________

## Features

The sqlite-web interface provides:

### 1. Schema Browser

- View all tables, columns, and types
- Inspect indexes and constraints
- See table statistics (row counts, sizes)

### 2. SQL Query Interface

- Execute custom SQL queries
- View query results in tabular format
- Export results to CSV/JSON
- View query execution plans (EXPLAIN QUERY PLAN)

### 3. Table Browser

- Browse table contents with pagination
- Filter and sort columns
- View individual row details
- Navigate foreign key relationships

### 4. Database Statistics

- Database file size
- Table sizes and row counts
- Index usage statistics
- WAL mode status

______________________________________________________________________

## Implementation

### 1. Add `--dev-mode` Flag

**File:** `pikaraoke/lib/args.py`

```python
parser.add_argument(
    "--dev-mode",
    action="store_true",
    help="Enable development features (database viewer, debug logging, etc.)",
    default=False,
)
```

### 2. Integrate sqlite-web Blueprint

**File:** `pikaraoke/app.py`

```python
from pikaraoke.lib.get_platform import get_data_directory
import os
import logging

logger = logging.getLogger(__name__)

# ... existing app initialization ...

# Development-only features
if args.dev_mode:
    logger.warning("Development mode enabled - DO NOT USE IN PRODUCTION")

    try:
        from sqlite_web import SqliteWebBlueprint

        db_path = os.path.join(get_data_directory(), "pikaraoke.db")

        # Only mount if database exists
        if os.path.exists(db_path):
            db_blueprint = SqliteWebBlueprint(
                database=db_path,
                name="dev_database",
                read_only=False,  # Allow modifications during development
                extension=None,  # No custom extensions
                password=None,  # Use existing auth
            )

            # Register blueprint with admin authentication
            from pikaraoke.lib.current_app import is_admin

            @db_blueprint.before_request
            def require_admin():
                if not is_admin():
                    from flask import redirect, url_for

                    return redirect(url_for("login"))

            app.register_blueprint(db_blueprint, url_prefix="/dev/database")
            logger.info("Development database viewer enabled at /dev/database")
        else:
            logger.warning(f"Database not found at {db_path}, skipping dev viewer")

    except ImportError:
        logger.warning("sqlite-web not installed. Run: uv add --dev sqlite-web")
```

______________________________________________________________________

## Security

### Multi-Layer Protection

1. **Flag-Based Activation**

   - Only available when `--dev-mode` flag is explicitly set
   - Flag must be passed every time the application starts
   - Default is OFF (secure by default)

2. **Authentication Required**

   - Reuses existing `@is_admin` decorator
   - Requires admin login before accessing viewer
   - Same authentication as other admin features

3. **Production Safety**

   - Never deployed to production (flag not passed)
   - No performance impact when disabled
   - Optional dependency (won't break if not installed)

4. **Clear Warnings**

   - Logs warning message when dev mode is enabled
   - Reminds developers this is for development only

### Security Checklist

- \[ \] `--dev-mode` flag defaults to False
- \[ \] Admin authentication required before access
- \[ \] Warning logged when dev mode is enabled
- \[ \] Documentation clearly states "development only"
- \[ \] Production deployment guides do not include `--dev-mode`

______________________________________________________________________

## Common Development Tasks

### Inspecting Database Schema

1. Navigate to `/dev/database`
2. Click on table name in left sidebar
3. View "Schema" tab to see CREATE TABLE statement

### Testing SQL Queries

1. Click "Query" tab
2. Enter SQL query (e.g., `SELECT * FROM songs LIMIT 10`)
3. Click "Execute" to run
4. Results display in table format

### Checking Database Integrity

```sql
PRAGMA integrity_check;
```

Expected result: `ok`

### Viewing Database Statistics

```sql
-- Table row counts
SELECT name, (SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=m.name) as tables
FROM sqlite_master m WHERE type='table';

-- Database size
SELECT page_count * page_size as size FROM pragma_page_count(), pragma_page_size();

-- Check WAL mode
PRAGMA journal_mode;
```

Expected WAL mode result: `wal`

### Exporting Test Data

1. Run query to get desired data
2. Click "Export" button
3. Choose CSV or JSON format
4. Save to file for use in unit tests

______________________________________________________________________

## Alternatives Considered

### Option 1: Standalone Desktop Tools

**Tools:** DB Browser for SQLite, DBeaver, DataGrip

**Pros:**

- Full-featured database clients
- Better performance for large datasets
- Richer visualization options

**Cons:**

- Requires separate installation
- Not integrated into PiKaraoke workflow
- Doesn't match web-based UI pattern
- Platform-specific (harder for cross-platform dev)

**Decision:** Rejected - prefer integrated solution

### Option 2: Custom Admin UI

**Approach:** Build custom database viewer in PiKaraoke admin panel

**Pros:**

- Fully integrated
- Tailored to PiKaraoke needs
- No external dependencies

**Cons:**

- Significant development time
- Reinventing the wheel
- Maintenance burden
- Out of scope for Stage 1

**Decision:** Deferred to Stage 3+ for user-facing features only

### Option 3: CLI Tools

**Tools:** `sqlite3` command-line client

**Pros:**

- No dependencies (built into Python)
- Lightweight
- Scriptable

**Cons:**

- Not user-friendly for visual inspection
- No web interface
- Harder to browse large result sets
- Doesn't fit Flask development workflow

**Decision:** Rejected - prefer web-based tool

______________________________________________________________________

## Development Workflow

### Typical Stage 1 Development Cycle

1. **Write database code** in `karaoke_database.py`
2. **Run unit tests** to validate logic
3. **Start app with dev mode**: `python -m pikaraoke --dev-mode`
4. **Open database viewer** at `/dev/database`
5. **Inspect results** of database operations
6. **Execute test queries** to verify data integrity
7. **Debug issues** by examining actual data
8. **Iterate** on implementation

### Example: Debugging Move Detection

**Scenario:** Testing file move/rename detection logic

**Steps:**

1. Create test files in download directory
2. Run `scan_library()` via unit test
3. Open `/dev/database` and check `songs` table:
   ```sql
   SELECT file_path, content_hash, last_modified
   FROM songs
   ORDER BY last_modified DESC
   LIMIT 10;
   ```
4. Move a file on disk
5. Run `scan_library()` again
6. Check database to verify:
   - Old path marked as deleted
   - New path added with same `content_hash`
   - Move detected correctly

______________________________________________________________________

## Removal Before Deployment

### Development Builds

```bash
# Dev mode enabled for local testing
python -m pikaraoke --dev-mode
```

### Production Builds

```bash
# No dev mode flag = no database viewer
python -m pikaraoke

# Or with production settings
python -m pikaraoke --port 80 --download-path /var/lib/pikaraoke/songs
```

### Verification

The database viewer is completely inactive unless:

1. `sqlite-web` is installed (dev dependency)
2. `--dev-mode` flag is explicitly passed
3. Database file exists at expected path

**Production checklist:**

- \[ \] No `--dev-mode` flag in startup scripts
- \[ \] No `sqlite-web` in production dependencies
- \[ \] `/dev/database` route returns 404 (not mounted)

______________________________________________________________________

## Troubleshooting

### Issue: "sqlite-web not installed" warning

**Cause:** Development dependency not installed

**Solution:**

```bash
uv add --dev sqlite-web
```

### Issue: Database viewer shows empty/no tables

**Cause:** Database not yet created or at wrong path

**Solution:**

1. Check database path:

   ```python
   from pikaraoke.lib.get_platform import get_data_directory
   import os

   print(os.path.join(get_data_directory(), "pikaraoke.db"))
   ```

2. Verify file exists:

   ```bash
   ls -lh <path-from-above>
   ```

3. If missing, run `scan_library()` to create it

### Issue: 403 Forbidden when accessing /dev/database

**Cause:** Not logged in as admin

**Solution:**

1. Navigate to `/login`
2. Log in with admin credentials
3. Return to `/dev/database`

### Issue: Changes not appearing in viewer

**Cause:** Browser caching or database not committed

**Solution:**

1. Refresh browser (Ctrl+F5 / Cmd+Shift+R)
2. Verify transactions are committed:
   ```python
   conn.commit()  # In your database code
   ```

______________________________________________________________________

## Future Enhancements

Potential improvements for later stages (optional):

1. **Query History**

   - Save frequently-used queries
   - Query templates for common tasks

2. **Data Visualization**

   - Charts for library statistics
   - Timeline view of database changes

3. **Schema Migrations Tracking**

   - Visual diff of schema changes
   - Migration history log

4. **Performance Profiling**

   - Slow query logging
   - Index usage analysis

**Note:** These are NOT required for Stage 1-4 completion. Focus remains on core database functionality.

______________________________________________________________________

## References

- [sqlite-web GitHub Repository](https://github.com/coleifer/sqlite-web)
- [SQLite Documentation](https://www.sqlite.org/docs.html)
- [Flask Blueprint Documentation](https://flask.palletsprojects.com/en/2.3.x/blueprints/)
- [PiKaraoke Database Implementation Plan](database-upgrade-implementation-plan.md)

______________________________________________________________________

**Document Status:** Complete
**Last Updated:** 2026-01-09
**Author:** Claude Code (based on user requirements)
**Next Steps:** Implement during Stage 1 development
