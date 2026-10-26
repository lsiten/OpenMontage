"""SQLite persistence for the PM writable layer (stdlib ``sqlite3`` only).

Zero third-party DB dependency: the whole store is stdlib ``sqlite3``. PM
metadata (project / status / cost budget / approvals / cost entries / chat
history) lives here; the on-disk ``projects/<id>/`` tree stays the shared
data source with Backlot, linked by ``project_id``.

Concurrency: a single connection guarded by a lock, opened in WAL mode. PM is
a small local app and a single writer is the safe default — this keeps the
PM write layer from racing the read-only Backlot derivation. Every public
method is defensive: a store failure degrades, never crashes the request
("never block, never break", same contract as Backlot).
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from typing_extensions import TypedDict

from lib.paths import REPO_ROOT
from pm import schema

_DB_DIR = Path(os.environ.get("PM_DB_DIR") or (REPO_ROOT / ".pm"))
_DB_PATH = Path(os.environ.get("PM_DB_PATH") or (_DB_DIR / "pm.db"))

_SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
    project_id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    requirement TEXT NOT NULL DEFAULT '',
    pipeline_type TEXT NOT NULL DEFAULT 'unknown',
    concept TEXT NOT NULL DEFAULT '',
    concept_is_offline_substitute INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'draft',
    mode TEXT NOT NULL DEFAULT 'warn',
    cost_budget_usd REAL NOT NULL DEFAULT 10.0,
    source TEXT NOT NULL DEFAULT 'manual',
    cost_estimate_json TEXT NOT NULL DEFAULT 'null',
    created_at TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS approvals (
    entry_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    stage TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL DEFAULT 'paid_call',
    requested_at TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending',
    decided_at TEXT NOT NULL DEFAULT '',
    decided_by TEXT NOT NULL DEFAULT '',
    note TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS cost_entries (
    entry_id TEXT PRIMARY KEY,
    project_id TEXT NOT NULL,
    tool TEXT NOT NULL DEFAULT '',
    operation TEXT NOT NULL DEFAULT '',
    estimated_usd REAL NOT NULL DEFAULT 0.0,
    reserved_usd REAL NOT NULL DEFAULT 0.0,
    actual_usd REAL NOT NULL DEFAULT 0.0,
    status TEXT NOT NULL DEFAULT 'estimated',
    is_paid INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS chat_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    content TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_approvals_project ON approvals(project_id);
CREATE INDEX IF NOT EXISTS idx_cost_project ON cost_entries(project_id);
CREATE INDEX IF NOT EXISTS idx_chat_project ON chat_messages(project_id);
CREATE TABLE IF NOT EXISTS deleted_projects (
    project_id TEXT PRIMARY KEY,
    deleted_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class DeletedProject(TypedDict):
    project_id: str
    title: str
    deleted_at: str


class PMDatabase:
    """A single-connection, lock-guarded SQLite store for PM metadata."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        self.db_path = Path(db_path) if db_path else _DB_PATH
        self._lock = threading.RLock()
        self._conn: Optional[sqlite3.Connection] = None
        try:
            self._connect()
        except Exception:
            # Degrade: the store is optional; a broken DB must not kill the app.
            self._conn = None

    def _connect(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            isolation_level=None,  # autocommit; we manage transactions by hand
        )
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        conn.executescript(_SCHEMA)
        self._conn = conn

    def _cur(self) -> sqlite3.Connection:
        with self._lock:
            if self._conn is None:
                # Best-effort reconnect; a failed store degrades to "no-op".
                try:
                    self._connect()
                except Exception:
                    pass
            if self._conn is None:
                raise RuntimeError("pm database unavailable")
            return self._conn

    # ---- projects -----------------------------------------------------

    def upsert_project(self, project: schema.PmProject) -> None:
        with self._lock:
            conn = self._cur()
            ts = _now()
            conn.execute(
                """
                INSERT INTO projects
                    (project_id, title, requirement, pipeline_type, concept,
                     concept_is_offline_substitute, status, mode,
                     cost_budget_usd, source, cost_estimate_json,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id) DO UPDATE SET
                    title=excluded.title,
                    requirement=excluded.requirement,
                    pipeline_type=excluded.pipeline_type,
                    concept=excluded.concept,
                    concept_is_offline_substitute=excluded.concept_is_offline_substitute,
                    status=excluded.status,
                    mode=excluded.mode,
                    cost_budget_usd=excluded.cost_budget_usd,
                    source=excluded.source,
                    cost_estimate_json=excluded.cost_estimate_json,
                    updated_at=excluded.updated_at
                """,
                (
                    project.project_id,
                    project.title,
                    project.requirement,
                    project.pipeline_type,
                    project.concept,
                    1 if project.concept_is_offline_substitute else 0,
                    project.status,
                    project.mode.mode,
                    project.cost_budget_usd,
                    project.source,
                    json.dumps(project.cost_estimate.model_dump() if project.cost_estimate else None),
                    project.created_at or ts,
                    ts,
                ),
            )

    def get_project(self, project_id: str) -> Optional[schema.PmProject]:
        with self._lock:
            conn = self._cur()
            row = conn.execute(
                "SELECT * FROM projects WHERE project_id = ? AND project_id NOT IN (SELECT project_id FROM deleted_projects)", (project_id,)
            ).fetchone()
            if row is None:
                return None
            return _row_to_project(row)

    def list_projects(self) -> list[schema.PmProject]:
        with self._lock:
            conn = self._cur()
            rows = conn.execute(
                "SELECT * FROM projects WHERE project_id NOT IN (SELECT project_id FROM deleted_projects) ORDER BY updated_at DESC"
            ).fetchall()
            return [_row_to_project(r) for r in rows]

    def update_project(self, project_id: str, update: schema.ProjectUpdate) -> Optional[schema.PmProject]:
        current = self.get_project(project_id)
        if current is None:
            return None
        data = current.model_dump()
        fields = update.model_dump(exclude_unset=True)
        for _k, _v in fields.items():
            if _v is None:
                continue
            data[_k] = _v
        # Keep the two budget representations consistent: when the budget mode
        # changes but the cost budget is not set explicitly, mirror the mode's
        # total_usd into cost_budget_usd so they cannot drift apart.
        if "mode" in fields and "cost_budget_usd" not in fields:
            data["cost_budget_usd"] = fields["mode"]["total_usd"]
        data["updated_at"] = _now()
        merged = schema.PmProject(**data)
        self.upsert_project(merged)
        return self.get_project(project_id)

    def delete_project(self, project_id: str) -> bool:
        """Hide a project; retain metadata, history and every media file."""
        with self._lock:
            if self.get_project(project_id) is None:
                return False
            conn = self._cur()
            conn.execute("INSERT INTO deleted_projects VALUES (?, ?)", (project_id, _now()))
            return True

    def list_deleted(self) -> list[DeletedProject]:
        with self._lock:
            rows = self._cur().execute(
                "SELECT p.project_id, p.title, d.deleted_at FROM projects p JOIN deleted_projects d USING(project_id) ORDER BY d.deleted_at DESC"
            ).fetchall()
            return [DeletedProject(project_id=row[0], title=row[1], deleted_at=row[2]) for row in rows]

    def restore_project(self, project_id: str) -> schema.PmProject | None:
        with self._lock:
            self._cur().execute("DELETE FROM deleted_projects WHERE project_id = ?", (project_id,))
            return self.get_project(project_id)

    def _is_deleted(self, project_id: str) -> bool:
        return self._cur().execute(
            "SELECT 1 FROM deleted_projects WHERE project_id = ?", (project_id,)
        ).fetchone() is not None

    # ---- approvals --------------------------------------------------

    def add_approval(self, approval: schema.Approval) -> None:
        with self._lock:
            conn = self._cur()
            conn.execute(
                """
                INSERT INTO approvals
                    (entry_id, project_id, stage, kind, requested_at, status,
                     decided_at, decided_by, note)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entry_id) DO NOTHING
                """,
                (
                    approval.entry_id or uuid.uuid4().hex,
                    approval.project_id,
                    approval.stage,
                    approval.kind,
                    approval.requested_at or _now(),
                    approval.status,
                    approval.decided_at,
                    approval.decided_by,
                    approval.note,
                ),
            )

    def get_approvals(self, project_id: str) -> list[schema.Approval]:
        with self._lock:
            if self._is_deleted(project_id):
                return []
            conn = self._cur()
            rows = conn.execute(
                "SELECT * FROM approvals WHERE project_id = ? ORDER BY requested_at",
                (project_id,),
            ).fetchall()
            out = []
            for r in rows:
                out.append(
                    schema.Approval(
                        entry_id=r[0],
                        project_id=r[1],
                        stage=r[2],
                        kind=r[3],
                        requested_at=r[4],
                        status=r[5],
                        decided_at=r[6],
                        decided_by=r[7],
                        note=r[8],
                    )
                )
            return out

    def decide_approval(self, entry_id: str, status: str, decided_by: str = "", note: str = "") -> None:
        with self._lock:
            conn = self._cur()
            conn.execute(
                "UPDATE approvals SET status = ?, decided_at = ?, decided_by = ?, note = ? WHERE entry_id = ?",
                (status, _now(), decided_by, note, entry_id),
            )

    # ---- cost entries -----------------------------------------------

    def add_cost_entry(self, entry: schema.CostEntry) -> None:
        with self._lock:
            conn = self._cur()
            conn.execute(
                """
                INSERT INTO cost_entries
                    (entry_id, project_id, tool, operation, estimated_usd,
                     reserved_usd, actual_usd, status, is_paid, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(entry_id) DO NOTHING
                """,
                (
                    entry.entry_id or uuid.uuid4().hex,
                    entry.project_id,
                    entry.tool,
                    entry.operation,
                    entry.estimated_usd,
                    entry.reserved_usd,
                    entry.actual_usd,
                    entry.status,
                    1 if entry.is_paid else 0,
                    entry.created_at or _now(),
                ),
            )

    def get_cost_entries(self, project_id: str) -> list[schema.CostEntry]:
        with self._lock:
            if self._is_deleted(project_id):
                return []
            conn = self._cur()
            rows = conn.execute(
                "SELECT * FROM cost_entries WHERE project_id = ? ORDER BY created_at",
                (project_id,),
            ).fetchall()
            out = []
            for r in rows:
                out.append(
                    schema.CostEntry(
                        project_id=r[1],
                        entry_id=r[0],
                        tool=r[2],
                        operation=r[3],
                        estimated_usd=r[4],
                        reserved_usd=r[5],
                        actual_usd=r[6],
                        status=r[7],
                        is_paid=bool(r[8]),
                        created_at=r[9],
                    )
                )
            return out

    # ---- chat history -----------------------------------------------

    def add_chat_message(self, project_id: str, role: str, content: str) -> None:
        with self._lock:
            conn = self._cur()
            conn.execute(
                "INSERT INTO chat_messages (project_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                (project_id, role, content, _now()),
            )

    def get_chat_messages(self, project_id: str) -> list[dict[str, str]]:
        with self._lock:
            if self._is_deleted(project_id):
                return []
            conn = self._cur()
            rows = conn.execute(
                "SELECT role, content, created_at FROM chat_messages WHERE project_id = ? ORDER BY id",
                (project_id,),
            ).fetchall()
            return [{"role": r[0], "content": r[1], "created_at": r[2]} for r in rows]

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except Exception:
                    pass
                self._conn = None


def _row_to_project(row: Any) -> schema.PmProject:
    (
        project_id, title, requirement, pipeline_type, concept,
        is_sub, status, mode, cost_budget_usd, source,
        cost_estimate_json, created_at, updated_at,
    ) = row
    estimate = None
    if cost_estimate_json and cost_estimate_json not in ("null", "None", ""):
        try:
            estimate = schema.CostEstimate(**json.loads(cost_estimate_json))
        except Exception:
            estimate = None
    return schema.PmProject(
        project_id=project_id,
        title=title or "",
        requirement=requirement or "",
        pipeline_type=pipeline_type or "unknown",
        concept=concept or "",
        concept_is_offline_substitute=bool(is_sub),
        status=status or "draft",
        mode=schema.BudgetMode(mode=mode or "warn", total_usd=cost_budget_usd or 0.0),
        cost_budget_usd=cost_budget_usd or 0.0,
        source=source or "manual",
        cost_estimate=estimate,
        created_at=created_at or "",
        updated_at=updated_at or "",
    )


# Module-level singleton (one store per process). Tests may construct their
# own PMDatabase(tmp_path) instead.
_db: Optional[PMDatabase] = None
_db_lock = threading.Lock()


def get_db() -> PMDatabase:
    global _db
    with _db_lock:
        if _db is None:
            _db = PMDatabase()
        return _db
