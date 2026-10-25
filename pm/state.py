"""PM view layer: reuse Backlot's read-only derivation, overlay PM metadata.

This is the "coexist + gradual upgrade" contract (§2). PM never rewrites
Backlot's read-only derived source files (checkpoints, artifacts, scene_plan,
asset_manifest, events.jsonl). For every read view it calls the SAME
Backlot derivation functions (``load_board_state`` / ``list_projects``) so
the two boards can't drift, then overlays the writable PM metadata (SQLite).

The only thing PM writes to a project directory is a ``pm`` segment inside
``project.json`` — a defensive read-modify-write that touches ONLY the
``pm`` key and leaves every Backlot-read key untouched.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from backlot.state import PROJECTS_DIR, list_projects, load_board_state
from pm import cost as cost_mod
from pm import schema
from pm.store import PMDatabase, get_db


# ---------------------------------------------------------------------------
# project.json PM segment (defensive — only the "pm" key)
# ---------------------------------------------------------------------------

def _project_dir(project_id: str) -> Path:
    return PROJECTS_DIR / project_id


def read_pm_segment(project_id: str) -> Optional[dict]:
    """Read the ``pm`` segment from project.json, if any. Never raises."""
    try:
        with open(_project_dir(project_id) / "project.json", encoding="utf-8") as f:
            marker = json.load(f)
        seg = marker.get("pm")
        return seg if isinstance(seg, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def write_pm_segment(project_id: str, project: schema.PmProject) -> None:
    """Write ONLY the ``pm`` segment into project.json (defensive, atomic).

    Backlot reads project.json for its marker (pipeline_type, title, …) but
    never writes it. PM adds a sibling ``pm`` key and leaves everything else
    intact, so the Backlot read-only contract and its regression baseline are
    preserved. The write is atomic (temp + rename) to avoid tearing a
    concurrent Backlot read.
    """
    path = _project_dir(project_id) / "project.json"
    marker: dict[str, Any] = {}
    try:
        with open(path, encoding="utf-8") as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            marker = loaded
    except (OSError, json.JSONDecodeError):
        marker = {}

    pm_seg = {
        "project_id": project.project_id,
        "status": project.status,
        "requirement": project.requirement,
        "pipeline_type": project.pipeline_type,
        "concept": project.concept,
        "concept_is_offline_substitute": project.concept_is_offline_substitute,
        "cost_budget_usd": project.cost_budget_usd,
        "source": project.source,
        "updated_at": project.updated_at,
    }
    schema.validate_pm_segment(pm_seg)
    marker["pm"] = pm_seg
    marker.setdefault("project_id", project.project_id)

    tmp = path.with_suffix(f".json.{__import__('uuid').uuid4().hex[:8]}")
    tmp.parent.mkdir(parents=True, exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(marker, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


# ---------------------------------------------------------------------------
# read views (Backlot derivation + PM metadata overlay)
# ---------------------------------------------------------------------------

def _pm_overlay(store: PMDatabase, project_id: str) -> dict:
    project = store.get_project(project_id)
    if project is None:
        return {"pm": None}
    return {
        "pm": {
            "title": project.title,
            "requirement": project.requirement,
            "pipeline_type": project.pipeline_type,
            "concept": project.concept,
            "concept_is_offline_substitute": project.concept_is_offline_substitute,
            "status": project.status,
            "cost_budget_usd": project.cost_budget_usd,
            "mode": project.mode.mode,
            "source": project.source,
            "created_at": project.created_at,
            "updated_at": project.updated_at,
            "cost_estimate": project.cost_estimate.model_dump() if project.cost_estimate else None,
        },
        "approvals": [a.model_dump() for a in store.get_approvals(project_id)],
        "cost_entries": [c.model_dump() for c in store.get_cost_entries(project_id)],
    }


def load_project_view(project_id: str, store: Optional[PMDatabase] = None) -> dict:
    """Detail view = Backlot read-only derivation + PM metadata overlay."""
    db = store or get_db()
    pdir = _project_dir(project_id)
    try:
        board = load_board_state(pdir) if pdir.is_dir() else {"project_id": project_id}
    except Exception:
        board = {"project_id": project_id, "error": "unreadable"}
    view = dict(board)
    view.update(_pm_overlay(db, project_id))
    return view


def list_project_views(store: Optional[PMDatabase] = None) -> list[dict]:
    """List view = Backlot library summaries + PM metadata overlay."""
    db = store or get_db()
    pm_rows = {p.project_id: p for p in db.list_projects()}
    views = []
    for summary in list_projects():
        pid = summary.get("project_id")
        pm = pm_rows.get(pid)
        merged = dict(summary)
        if pm is not None:
            merged["pm_status"] = pm.status
            merged["pm_source"] = pm.source
            merged["cost_budget_usd"] = pm.cost_budget_usd
            merged["requirement"] = pm.requirement
        views.append(merged)
    return views


def cost_view(project_id: str, store: Optional[PMDatabase] = None) -> dict:
    """Cost view: PM budget + entries + Backlot-derived cost + local/paid."""
    db = store or get_db()
    project = db.get_project(project_id)
    entries = db.get_cost_entries(project_id)
    pdir = _project_dir(project_id)
    try:
        board = load_board_state(pdir) if pdir.is_dir() else {}
    except Exception:
        board = {}
    derived = board.get("cost") or {}
    budget_total = project.cost_budget_usd if project else 10.0
    reserved = sum(e.reserved_usd for e in entries)
    spent = sum(e.actual_usd for e in entries)
    return {
        "project_id": project_id,
        "budget_total_usd": budget_total,
        "mode": project.mode.mode if project else "warn",
        "reserved_usd": round(reserved, 4),
        "spent_usd": round(spent, 4),
        "remaining_usd": round(max(0.0, budget_total - spent), 4),
        "derived_from_pipeline": derived,
        "entries": [e.model_dump() for e in entries],
        "cost_estimate": project.cost_estimate.model_dump() if project and project.cost_estimate else None,
    }


def status_view(project_id: str, store: Optional[PMDatabase] = None) -> dict:
    """Status view: PM lifecycle + Backlot live/active stage + approvals."""
    db = store or get_db()
    project = db.get_project(project_id)
    pdir = _project_dir(project_id)
    try:
        board = load_board_state(pdir) if pdir.is_dir() else {}
    except Exception:
        board = {}
    approvals = db.get_approvals(project_id)
    pending = [a for a in approvals if a.status == "pending"]
    return {
        "project_id": project_id,
        "pm_status": project.status if project else None,
        "live": board.get("live", False),
        "last_activity": board.get("last_activity", 0),
        "active_stage": board.get("active_stage"),
        "awaiting_human": board.get("awaiting_human", False),
        "pending_approvals": len(pending),
        "approvals": [a.model_dump() for a in approvals],
    }


def capability_menu(registry: Optional[object] = None) -> dict:
    """The provider-menu capability report (local vs paid), for the chat/UI."""
    return cost_mod.build_capability_report(registry)
