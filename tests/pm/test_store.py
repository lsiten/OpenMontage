"""SQLite store tests (stdlib sqlite3, no third-party DB)."""

from __future__ import annotations

from pm.store import PMDatabase
from pm import schema


def _proj(pid="p1", **kw):
    base = dict(project_id=pid, title="T", requirement="req", pipeline_type="cinematic",
                concept="c", status="draft", source="manual")
    base.update(kw)
    return schema.PmProject(**base)


def test_upsert_and_get(db: PMDatabase):
    p = _proj()
    db.upsert_project(p)
    got = db.get_project("p1")
    assert got is not None
    assert got.project_id == "p1"
    assert got.status == "draft"


def test_upsert_is_idempotent(db: PMDatabase):
    db.upsert_project(_proj())
    db.upsert_project(_proj())
    assert len(db.list_projects()) == 1


def test_update_project_revalidates_mode(db: PMDatabase):
    db.upsert_project(_proj(mode=schema.BudgetMode(mode="warn", total_usd=10.0)))
    updated = db.update_project("p1", schema.ProjectUpdate(status="in_progress",
                                                          mode=schema.BudgetMode(mode="cap", total_usd=5.0)))
    assert updated is not None
    assert updated.status == "in_progress"
    assert updated.mode.mode == "cap"          # re-validated into a BudgetMode, not a dict
    assert updated.cost_budget_usd == 5.0


def test_update_unknown_returns_none(db: PMDatabase):
    assert db.update_project("nope", schema.ProjectUpdate(status="done")) is None


def test_delete_cascades(db: PMDatabase):
    db.upsert_project(_proj())
    db.add_approval(schema.Approval(project_id="p1", kind="paid_call"))
    db.add_cost_entry(schema.CostEntry(project_id="p1", entry_id="e1"))
    db.add_chat_message("p1", "user", "hi")
    assert db.delete_project("p1") is True
    assert db.get_project("p1") is None
    assert db.get_approvals("p1") == []
    assert db.get_cost_entries("p1") == []
    assert db.get_chat_messages("p1") == []
    assert db.delete_project("p1") is False


def test_approvals_roundtrip_and_decide(db: PMDatabase):
    db.add_approval(schema.Approval(project_id="p1", kind="paid_call", status="pending"))
    rows = db.get_approvals("p1")
    assert len(rows) == 1
    eid = rows[0].entry_id
    assert eid  # an id was generated
    db.decide_approval(eid, "approved", decided_by="lead")
    rows = db.get_approvals("p1")
    assert rows[0].status == "approved"
    assert rows[0].decided_by == "lead"
    assert rows[0].entry_id == eid


def test_cost_entries_roundtrip(db: PMDatabase):
    db.add_cost_entry(schema.CostEntry(project_id="p1", entry_id="e1", tool="t",
                                       estimated_usd=1.0, reserved_usd=1.0, status="reserved", is_paid=True))
    rows = db.get_cost_entries("p1")
    assert len(rows) == 1
    assert rows[0].reserved_usd == 1.0
    assert rows[0].is_paid is True


def test_chat_messages_roundtrip(db: PMDatabase):
    db.add_chat_message("p1", "user", "hello")
    db.add_chat_message("p1", "assistant", "ok")
    msgs = db.get_chat_messages("p1")
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[1]["content"] == "ok"
