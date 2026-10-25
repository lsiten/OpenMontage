"""PM write-model persistence — SQLite (stdlib, zero third-party deps).

The PM layer persists its *writable* metadata in a single SQLite database and
associates every row with a runtime ``projects/<id>/`` directory by
``project_id``. Nothing here touches the Backlot read-only derive sources
(checkpoint_* / artifact files / events.jsonl); those remain owned by the
pipeline. Backlot derives its live board from those files; PM derives nothing
it writes — it only reads via ``backlot.state`` and writes its own tables.

The database location is overridable via ``OPENMONTAGE_PM_DB`` so tests and
staging can point at an isolated file; the default lives under ``.pm/`` (the
design doc's recommended isolated location, never the source tree).
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from lib.paths import REPO_ROOT


def db_path() -> Path:
    """Canonical PM SQLite location (env-overridable, like PROJECTS_DIR)."""
    override = os.environ.get("OPENMONTAGE_PM_DB")
    if override:
        return Path(override)
    return REPO_ROOT / ".pm" / "db.sqlite"


# DDL. All timestamps are ISO-8601 UTC strings written by the store layer so
# the DB stays portable and human-readable (no server-side clock dependence).
SCHEMA = """
CREATE TABLE IF NOT EXISTS pm_projects (
    project_id      TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    pipeline_type   TEXT NOT NULL,
    concept         TEXT,
    status          TEXT NOT NULL DEFAULT 'draft',
    render_runtime  TEXT,
    cost_budget_usd REAL NOT NULL DEFAULT 0,
    cost_reserved_usd REAL NOT NULL DEFAULT 0,
    cost_spent_usd  REAL NOT NULL DEFAULT 0,
    cost_mode       TEXT NOT NULL DEFAULT 'warn',
    requires_approval INTEGER NOT NULL DEFAULT 0,
    approved        INTEGER NOT NULL DEFAULT 0,
    created_by      TEXT,
    requirement     TEXT,
    notes         TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pm_approvals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    TEXT NOT NULL,
    kind          TEXT NOT NULL,
    detail        TEXT,
    status        TEXT NOT NULL DEFAULT 'pending',
    requested_by  TEXT,
    decided_by    TEXT,
    created_at    TEXT NOT NULL,
    decided_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_pm_approvals_project
    ON pm_approvals (project_id);

CREATE TABLE IF NOT EXISTS pm_artifacts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id    TEXT NOT NULL,
    name          TEXT NOT NULL,
    kind          TEXT,
    path          TEXT,
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_pm_artifacts_project
    ON pm_artifacts (project_id);

CREATE TABLE IF NOT EXISTS pm_chats (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    requirement   TEXT NOT NULL,
    pipeline_type TEXT,
    concept       TEXT,
    cost_estimate TEXT,
    approval_items TEXT,
    created_at    TEXT NOT NULL
);
"""


def connect(path: Optional[Path] = None) -> sqlite3.Connection:
    """Open a connection to the PM database and ensure the schema exists."""
    p = Path(path) if path else db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    # check_same_thread=False: the single lock-guarded connection is shared
    # across FastAPI threadpool workers; the RLock in the store layer
    # serializes all access, so cross-thread use is safe.
    conn = sqlite3.connect(str(p), timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


@contextmanager
def open_db(path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    """Context manager that yields a connection and commits/closes it."""
    conn = connect(path)
    try:
        yield conn
    finally:
        conn.close()
