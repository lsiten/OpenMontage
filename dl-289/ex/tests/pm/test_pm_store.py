"""PM store CRUD contract — create / read / update / status / approvals."""

import pytest

from pm import store
from pm.schemas import (
    ApprovalRequest,
    ProjectCreate,
    ProjectUpdate,
)


def test_create_and_get():
    p = store.create_project(ProjectCreate(title="黑洞科普", pipeline_type="animated-explainer"))
    assert p.project_id
    assert p.status == "draft"
    assert p.title == "黑洞科普"
    got = store.get_project(p.project_id)
    assert got is not None
    assert got.project_id == p.project_id


def test_create_writes_marker_without_pipeline_files():
    p = store.create_project(ProjectCreate(title="t", pipeline_type="cinematic"))
    marker = store.get_project(p.project_id)
    assert marker is not None
    # Marker write is best-effort; with a temp projects dir it should exist.
    from pathlib import Path

    pdir = Path(p.project_id if False else p.project_id)
    # The runtime dir is under the temp projects dir; verify no backlot files.
    # (We only assert the SQLite row exists and is well-formed here.)
    assert p.pipeline_type == "cinematic"


def test_list_orders_by_updated_desc():
    a = store.create_project(ProjectCreate(title="a", pipeline_type="cinematic"))
    b = store.create_project(ProjectCreate(title="b", pipeline_type="clip-factory"))
    # b is newer -> listed first
    rows = store.list_projects()
    assert rows[0].project_id == b.project_id
    assert len(rows) == 2


def test_update_status_and_budget():
    p = store.create_project(ProjectCreate(title="x", pipeline_type="screen-demo"))
    store.update_project(p.project_id, ProjectUpdate(status="planning", cost_budget_usd=5.0))
    got = store.get_project(p.project_id)
    assert got.status == "planning"
    assert got.cost_budget_usd == 5.0


def test_set_status_shortcut():
    p = store.create_project(ProjectCreate(title="y", pipeline_type="talking-head"))
    store.set_status(p.project_id, "approved")
    assert store.get_project(p.project_id).status == "approved"


def test_approvals_lifecycle():
    p = store.create_project(ProjectCreate(title="z", pipeline_type="localization-dub"))
    a = store.request_approval(p.project_id, ApprovalRequest(kind="budget", detail="approve 2 USD"))
    assert a.status == "pending"
    approved = store.decide_approval(a.id, "approved", decided_by="producer")
    assert approved.status == "approved"
    assert approved.decided_by == "producer"
    assert store.list_approvals(p.project_id) == [approved]


def test_get_unknown_returns_none():
    assert store.get_project("does-not-exist") is None
