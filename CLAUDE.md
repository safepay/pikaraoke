# CLAUDE.md

Guidance for Claude Code when working on PiKaraoke. The [development guide](https://github.com/vicwomg/pikaraoke/wiki/Pikaraoke-development-guide) owns contributor process: raising an issue, scope, setup, releases. This file owns what a code change can invalidate and what gates CI, and points at a tracked config rather than restating what it already encodes.

## Project Overview

PiKaraoke is a karaoke system for Raspberry Pi, Windows, macOS, and Linux. Web interface for YouTube song search, queuing, and playback with pitch shifting and streaming.

## Core Principles

**Single-owner maintainability:** Code clarity over documentation. Simplicity over flexibility. One source of truth.

## Project Layout

```text
pikaraoke/
  app.py                   # Flask init, blueprint registration, server startup
  karaoke.py               # Coordinator - wires managers and events
  constants.py             # LANGUAGES dict
  version.py               # __version__

  lib/                     # Business logic (no Flask imports except flask_babel._)
    karaoke_database.py    #   SQLite data layer (songs table, WAL mode)
    library_scanner.py     #   FS-to-DB sync with move detection & circuit breaker
    song_manager.py        #   Song CRUD via DB + filesystem
    song_list.py           #   Hybrid set/sorted-list for in-memory lookups
    play_history_manager.py #  Sessions and plays, and the rankings over them
    metadata_parser.py     #   YouTube ID extraction & filename tidying
    ...                    #   (see the files for the rest)

  routes/                  # Flask blueprints (thin delegation layer)
  templates/               # Jinja2 (base.html is the master layout)
  static/                  # CSS (Bulma), JS, fonts, icons, images
  translations/            # i18n via flask-babel

tests/
  conftest.py              # Shared fixtures
  unit/                    # All tests here (test_<module_name>.py)
```

## Architecture

**SQLite database.** `pikaraoke.db` lives in the platform data directory. `_SCHEMA` at the top of `lib/karaoke_database.py` is the authority on tables and columns; `KaraokeDatabase` is the pure data layer over it. WAL mode, schema version in `PRAGMA user_version`. `LibraryScanner` syncs filesystem to DB, diffing against DB paths and detecting moves by basename. A circuit breaker (`CIRCUIT_BREAKER_THRESHOLD = 0.5`) prevents mass deletion when a song drive is unmounted. Cold start scans fully before the UI is ready; otherwise it loads instantly and syncs in the background.

**Manager pattern.** Managers take explicit dependencies (PreferenceManager, EventSystem, KaraokeDatabase), never the Karaoke instance. Karaoke wires them together and subscribes to events.

**Events.** Components emit; Karaoke subscribes and broadcasts to the UI via SocketIO. See `karaoke.py` for subscriptions, `events.py` for the dispatcher.

**Route blueprints.** `flask_smorest.Blueprint`, never `flask.Blueprint`. `app.py` holds both lists: `_api_blueprints` register on `api` and show in `/apidocs`, `_internal_blueprints` on `app` and do not. Membership is readership, not medium - an internal blueprint may still carry an `/api/` route. Validate with `@bp.arguments(Schema, location="query")`; the route receives a `params` dict. HTML form fields are snake_case. Routes delegate to managers - no business logic.

**A route's medium is its path.** Every route answering JSON sits under `/api`, and no page does. The auth gate reads nothing else to choose between a JSON 403 and a redirect, so putting a JSON route outside `/api` hands a guest HTML where the caller reads JSON. Nothing tests this - it holds by review only. `install_auth_gate(app)` runs in `app.py` after registration, so every endpoint it reads exists; `@public` from `lib/auth.py` opens a route to the room, below its `@route`, and anything unmarked is host-only.

**File paths.** Always `str(path)`, never `path.as_posix()`, which breaks on Windows. Paths are stored in the DB as native OS strings; `SongList` is rebuilt from them on startup.

## Filename Conventions

YouTube video filenames use exactly 11-character IDs:

- PiKaraoke format: `Title---dQw4w9WgXcQ.mp4` (triple dash)
- yt-dlp format: `Title [dQw4w9WgXcQ].mp4` (brackets)

Only support these two patterns.

## Error Handling

- Catch specific exceptions, never bare `except:`
- Log errors, never swallow silently
- Use context managers for resources

## Code Style

Formatting is enforced, not remembered - `code_quality/.pre-commit-config.yaml` holds Black (100 char), isort, pycln, pylint and mdformat.

- Type hints required: modern syntax (`str | None`) — Python 3.10+ is the minimum, no `from __future__ import annotations` needed
- Concise docstrings for public APIs - explain "why", not "how"
- Comments say what the code cannot: a measured number, a rejected alternative, a platform quirk. State it once, at the definition, and prune any comment an edit makes wrong.
- No emoji or unicode emoji substitutes

## Testing

Mock external I/O and subprocess calls. Tests live in `tests/unit/` as `test_<module_name>.py`.

- Test business logic and integration points; skip trivial getters/setters
- Skip the test entirely when a fix is self-evident and cannot silently regress
- Use real `EventSystem` and `PreferenceManager` instances (they're lightweight)

## CI gates

```bash
uv run pytest
uv run pre-commit run --config code_quality/.pre-commit-config.yaml --all-files
```

- Never commit to `master` - the `no-commit-to-branch` hook refuses it.
- Commit subjects must pass commitlint, which runs in CI only. `.commitlintrc.yml` extends `@commitlint/config-conventional`.
- A PR title becomes the squash subject `<title> (#N)`, so a leading `# ` comments the whole subject out and fails commitlint.
- `feat`, `fix`, `perf` and `docs` reach the release notes; the rest are hidden. Use `chore` for housekeeping no user reads about.
- Issues follow the templates in `.github/ISSUE_TEMPLATE/`.
