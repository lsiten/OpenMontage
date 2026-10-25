"""Contract tests for the PM (production-manager) package.

These assert the hard, contract-level invariants of the PM layer and are
written so they can never weaken the Backlot read-only contract
(test_backlot_contract.py) — PM only ever touches the ``pm`` key of
project.json and never calls or reserves a paid provider.
"""

from __future__ import annotations

import json

from pm import chat as chat_mod
from pm import cost as cost_mod
from pm import pipeline_select as selector
from pm import schema
from pm import state as state_mod


class _FakeRegistry:
    """A deterministic provider menu for contract assertions."""

    def provider_menu(self):
        return {
            "video_generation": {
                "available": [
                    {"name": "remotion", "provider": "remotion", "runtime": "local",
                     "status": "available", "best_for": ["local render"]},
                ],
                "unavailable": [
                    {"name": "veo", "provider": "veo", "runtime": "api",
                     "status": "unavailable", "best_for": "cloud video"},
                ],
            },
            "audio": {
                "available": [
                    {"name": "piper", "provider": "piper", "runtime": "local",
                     "status": "available", "best_for": ["tts"]},
                ],
                "unavailable": [
                    {"name": "elevenlabs", "provider": "elevenlabs", "runtime": "api",
                     "status": "unavailable", "best_for": ["tts"]},
                ],
            },
        }


def test_thirteen_pipelines_reused():
    # Contract §0/§3: exactly the 13 agentic pipelines, nothing more or less.
    assert len(selector.KNOWN_PIPELINES) == 13
    assert "cinematic" in selector.KNOWN_PIPELINES
    assert "screen-demo" in selector.KNOWN_PIPELINES
    assert "talking-head" in selector.KNOWN_PIPELINES


def test_provider_menu_classifies_local_and_paid():
    rep = cost_mod.build_capability_report(_FakeRegistry())
    local = {c.provider for c in rep["local"]}
    paid = {c.provider for c in rep["paid"]}
    assert "remotion" in local
    assert "piper" in local
    assert "veo" in paid
    assert "elevenlabs" in paid
    # every paid capability is shown as 未接入/需授权 (never run)
    for c in rep["paid"]:
        assert c.is_paid is True
        assert c.status_label == cost_mod.STATUS_LABEL_UNCONFIGURED
    # a local capability is never marked paid
    for c in rep["local"]:
        assert c.is_local is True
        assert c.is_paid is False


def test_zero_paid_boundary_fake_and_real_registry():
    # Fake registry: never a paid dollar figure.
    est = cost_mod.estimate_cost("cinematic", registry=_FakeRegistry())
    assert est.total_paid_usd == 0.0
    assert est.total_local_usd == 0.0
    # Real registry: still never a paid dollar figure.
    est2 = cost_mod.estimate_cost("talking-head", registry=None)
    assert est2.total_paid_usd == 0.0


def test_proposal_is_offline_substitute_not_real_ai():
    p = chat_mod.build_proposal("make a cinematic short film", registry=_FakeRegistry())
    assert p.is_offline_substitute is True
    assert chat_mod.OFFLINE_SUBSTITUTE_BANNER in p.concept
    assert p.cost_estimate.total_paid_usd == 0.0
    # a sensitive-content boundary item is always present
    assert any(it.kind == "sensitive" for it in p.human_approval_items)


def test_pm_segment_only_touches_pm_key(monkeypatch, tmp_path):
    """Backlot coexistence: PM must only add/modify the ``pm`` key."""
    projects = tmp_path / "projects"
    pdir = projects / "p1"
    pdir.mkdir(parents=True)
    # Pre-existing Backlot-read marker + a backlot key PM must NOT touch.
    backlot_marker = {
        "project_id": "p1",
        "title": "Backlot title",
        "pipeline_type": "cinematic",
        "scene_plan_ref": "scene_plan.json",
    }
    (pdir / "project.json").write_text(json.dumps(backlot_marker), encoding="utf-8")
    monkeypatch.setattr(state_mod, "PROJECTS_DIR", projects)

    project = schema.PmProject(
        project_id="p1", title="PM title", requirement="req",
        pipeline_type="cinematic", status="proposed", cost_budget_usd=10.0,
    )
    state_mod.write_pm_segment("p1", project)

    after = json.loads((pdir / "project.json").read_text(encoding="utf-8"))
    # Backlot-read keys are untouched.
    assert after["title"] == "Backlot title"
    assert after["pipeline_type"] == "cinematic"
    assert after["scene_plan_ref"] == "scene_plan.json"
    # Only a pm segment was added.
    assert "pm" in after
    assert after["pm"]["status"] == "proposed"
    # The pm segment validates against the PM JSON schema.
    schema.validate_pm_segment(after["pm"])
