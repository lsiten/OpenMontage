"""PM write-model CRUD — the only writable layer for PM metadata.

A thin, thread-safe CRUD layer over the SQLite write model in :mod:`pm.db`.
It owns project creation / status / cost budget / approvals / artifact index /
chat history. It NEVER writes Backlot's read-only derive files; it only creates
the runtime ``projects/<id>/`` directory + a ``project.json`` *marker* (which
Backlot already reads as a marker) plus the PM metadata rows in SQLite.

Thread-safety: FastAPI serves requests from a thread pool, so all access goes
through a single lock-guarded connection. SQLite serializes writes; the lock
keeps the single connection safe across worker threads.
"""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import sqlite3

from pm.db import connect, db_path
from pm.schemas import (
    ApprovalRequest,
    ApprovalResponse,
    ProjectCreate,
    ProjectResponse,
    ProjectUpdate,
)

_lock = threading.RLock()
# RLock (reentrant): create_project holds this lock and then calls
# _make_project_id, which acquires it again on the same thread; a
# non-reentrant Lock would self-deadlock and hang the write path.
_conn: Optional[sqlite3.Connection] = None
_path: Optional[Path] = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure() -> sqlite3.Connection:
    global _conn, _path
    if _conn is None:
        _path = db_path()
        _conn = connect(_path)
    return _conn


def reset(path: Optional[Path] = None) -> None:
    """Close the cached connection (used by tests to point at a temp db)."""
    global _conn, _path
    if _conn is not None:
        _conn.close()
        _conn = None
        _path = None


def _row_to_response(row: sqlite3.Row) -> ProjectResponse:
    return ProjectResponse(
        project_id=row["project_id"],
        title=row["title"],
        pipeline_type=row["pipeline_type"],
        concept=row["concept"],
        status=row["status"],
        render_runtime=row["render_runtime"],
        cost_budget_usd=float(row["cost_budget_usd"]),
        cost_reserved_usd=float(row["cost_reserved_usd"]),
        cost_spent_usd=float(row["cost_spent_usd"]),
        cost_mode=row["cost_mode"],
        requires_approval=bool(row["requires_approval"]),
        approved=bool(row["approved"]),
        requirement=row["requirement"],
        created_by=row["created_by"],
        notes=row["notes"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _slugify(text: str, maxlen: int = 40) -> str:
    import re

    s = re.sub(r"[^a-z0-9]+", "-", text.lower().strip())
    s = s.strip("-")[:maxlen].strip("-")
    return s or "project"


def _make_project_id(pipeline_type: str, title: str, conn: sqlite3.Connection) -> str:
    """Generate a unique, human-readable project id (never collides)."""
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = f"{_slugify(title) or 'project'}-{_slugify(pipeline_type, 20)}-{stamp}"
    candidate = base[:60]
    with _lock:
        n = 0
        while True:
            pid = candidate if n == 0 else f"{candidate}-{n}"
            row = conn.execute(
                "SELECT 1 FROM pm_projects WHERE project_id = ?", (pid,)
            ).fetchone()
            if row is None:
                return pid
            n += 1


def _write_project_marker(
    projects_dir: Path, project_id: str, resp: ProjectResponse
) -> None:
    """Create the runtime project directory + a Backlot-compatible marker.

    Backlot's state.py reads ``project.json`` as a *marker* (title,
    pipeline_type, created_at). We write only that marker + a ``pm`` segment;
    we never write Backlot's read-only derive files (checkpoints/artifacts/
    events.jsonl). This is the PM->Backlot association point.
    """
    pdir = Path(projects_dir) / project_id
    pdir.mkdir(parents=True, exist_ok=True)
    marker = {
        "title": resp.title,
        "pipeline_type": resp.pipeline_type,
        "created_at": resp.created_at,
        "pm": {
            "status": resp.status,
            "render_runtime": resp.render_runtime,
            "cost_budget_usd": resp.cost_budget_usd,
            "cost_mode": resp.cost_mode,
            "requires_approval": resp.requires_approval,
            "approved": resp.approved,
        },
    }
    (pdir / "project.json").write_text(
        json.dumps(marker, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# --------------------------------------------------------------------------
# CRUD
# --------------------------------------------------------------------------

def create_project(
    data: ProjectCreate,
    projects_dir: Optional[Path] = None,
    write_marker: bool = True,
) -> ProjectResponse:
    """Create a project (SQLite row + optional runtime dir + marker)."""
    from lib.paths import PROJECTS_DIR

    with _lock:
        conn = _ensure()
        now = _now()
        pid = _make_project_id(data.pipeline_type, data.title, conn)
        conn.execute(
            """
            INSERT INTO pm_projects (
                project_id, title, pipeline_type, concept, status, render_runtime,
                cost_budget_usd, cost_reserved_usd, cost_spent_usd, cost_mode,
                requires_approval, approved, created_by, requirement, notes,
                created_at, updated_at
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                pid, data.title, data.pipeline_type, data.concept, "draft",
                data.render_runtime, data.cost_budget_usd, 0.0, 0.0,
                data.cost_mode, 1 if data.requires_approval else 0, 0,
                data.created_by, data.requirement, data.notes, now, now,
            ),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM pm_projects WHERE project_id = ?", (pid,)
        ).fetchone()
        resp = _row_to_response(row)
        if write_marker:
            try:
                _write_project_marker(
                    Path(projects_dir) if projects_dir else PROJECTS_DIR,
                    pid, resp,
                )
            except Exception:
                # Marker write is best-effort; the SQLite row is the source of
                # truth. A missing runtime dir must not fail project creation.
                pass
        return resp


def get_project(project_id: str) -> Optional[ProjectResponse]:
    with _lock:
        conn = _ensure()
        row = conn.execute(
            "SELECT * FROM pm_projects WHERE project_id = ?", (project_id,)
        ).fetchone()
        return _row_to_response(row) if row else None


def list_projects() -> list[ProjectResponse]:
    with _lock:
        conn = _ensure()
        rows = conn.execute(
            "SELECT * FROM pm_projects ORDER BY updated_at DESC"
        ).fetchall()
        return [_row_to_response(r) for r in rows]


def update_project(project_id: str, data: ProjectUpdate) -> Optional[ProjectResponse]:
    fields = data.model_dump(exclude_none=True)
    # The write schema has no updated_by column; drop the audit hint so the
    # remaining field placeholders line up with the SQL (status/..., updated_at, project_id).
    fields.pop("updated_by", None)
    if not fields:
        return get_project(project_id)
    set_sql = ", ".join(f"{k} = ?" for k in fields)
    args = list(fields.values()) + [_now(), project_id]
    with _lock:
        conn = _ensure()
        conn.execute(
            f"UPDATE pm_projects SET {set_sql}, updated_at = ? WHERE project_id = ?",
            args,
        )
        conn.commit()
    return get_project(project_id)


def set_status(project_id: str, status: str, updated_by: Optional[str] = None) -> Optional[ProjectResponse]:
    return update_project(project_id, ProjectUpdate(status=status, updated_by=updated_by))


# --------------------------------------------------------------------------
# Approvals
# --------------------------------------------------------------------------

def request_approval(project_id: str, data: ApprovalRequest) -> ApprovalResponse:
    with _lock:
        conn = _ensure()
        now = _now()
        cur = conn.execute(
            """
            INSERT INTO pm_approvals
                (project_id, kind, detail, status, requested_by, created_at, decided_at)
            VALUES (?,?,?,?,?,?,?)
            """,
            (project_id, data.kind, data.detail, "pending", data.requested_by, now, None),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM pm_approvals WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return _approval_response(row)


def decide_approval(
    approval_id: int,
    status: str,
    decided_by: Optional[str] = None,
) -> Optional[ApprovalResponse]:
    with _lock:
        conn = _ensure()
        now = _now()
        conn.execute(
            "UPDATE pm_approvals SET status = ?, decided_by = ?, decided_at = ? WHERE id = ?",
            (status, decided_by or "system", now, approval_id),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM pm_approvals WHERE id = ?", (approval_id,)
        ).fetchone()
        return _approval_response(row) if row else None


def list_approvals(project_id: str) -> list[ApprovalResponse]:
    with _lock:
        conn = _ensure()
        rows = conn.execute(
            "SELECT * FROM pm_approvals WHERE project_id = ? ORDER BY id",
            (project_id,),
        ).fetchall()
        return [_approval_response(r) for r in rows]


def _approval_response(row: sqlite3.Row) -> ApprovalResponse:
    return ApprovalResponse(
        id=row["id"],
        project_id=row["project_id"],
        kind=row["kind"],
        detail=row["detail"],
        status=row["status"],
        requested_by=row["requested_by"],
        decided_by=row["decided_by"],
        created_at=row["created_at"],
        decided_at=row["decided_at"],
    )


# --------------------------------------------------------------------------
# Artifacts
# --------------------------------------------------------------------------

def add_artifact(project_id: str, name: str, kind: str, path: Optional[str] = None) -> None:
    with _lock:
        conn = _ensure()
        conn.execute(
            "INSERT INTO pm_artifacts (project_id, name, kind, path, created_at) VALUES (?,?,?,?,?)",
            (project_id, name, kind, path, _now()),
        )
        conn.commit()


def list_artifacts(project_id: str) -> list[dict[str, Any]]:
    with _lock:
        conn = _ensure()
        rows = conn.execute(
            "SELECT * FROM pm_artifacts WHERE project_id = ? ORDER BY id",
            (project_id,),
        ).fetchall()
        return [dict(r) for r in rows]
