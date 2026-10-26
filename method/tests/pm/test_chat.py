"""Conversational driver tests (contract §3).

The chat driver reuses the 13-pipeline selection and the registry provider
menu, and turns a requirement into a *proposal* (never an execution). It
must never call a paid provider, never impersonate a real AI, and must
label its output as an offline substitute.
"""

from __future__ import annotations

from pm import chat as chat_mod
from pm import pipeline_select as selector


class _FakeRegistry:
    def provider_menu(self):
        return {
            "video_generation": {
                "available": [
                    {"name": "remotion", "provider": "remotion", "runtime": "local",
                     "status": "available", "best_for": ["x"]},
                ],
                "unavailable": [
                    {"name": "veo", "provider": "veo", "runtime": "api",
                     "status": "unavailable", "best_for": "y"},
                ],
            },
            "tts": {
                "available": [
                    {"name": "piper", "provider": "piper", "runtime": "local",
                     "status": "available", "best_for": ["tts"]},
                ],
                "unavailable": [],
            },
        }


def test_build_proposal_is_offline_substitute():
    p = chat_mod.build_proposal("product promo animation", registry=_FakeRegistry())
    assert p.is_offline_substitute is True
    assert chat_mod.OFFLINE_SUBSTITUTE_BANNER in p.concept
    # zero paid
    assert p.cost_estimate.total_paid_usd == 0.0
    # a sensitive-content boundary item is always present
    assert any(it.kind == "sensitive" for it in p.human_approval_items)
    # paid capabilities are named as approval items, not run
    assert any(it.kind == "paid_call" for it in p.human_approval_items)
    # selection came from the reused 13-pipeline selector
    assert p.selection.pipeline_type in selector.KNOWN_PIPELINES


def test_build_proposal_pipeline_override():
    p = chat_mod.build_proposal("anything", pipeline_override="cinematic")
    assert p.pipeline_type == "cinematic"
    assert "覆盖自动选择" in p.selection.reason


def test_build_proposal_invalid_override_uses_auto_selection():
    p = chat_mod.build_proposal("make a cinematic short film",
                                pipeline_override="not-a-real-pipeline")
    assert p.pipeline_type in selector.KNOWN_PIPELINES


def test_generate_concept_has_banner():
    sel = selector.select_pipeline("a short film")
    c = chat_mod.generate_concept("a short film", "cinematic", sel)
    assert chat_mod.OFFLINE_SUBSTITUTE_BANNER in c


def test_chat_session_create_project(db, projects_dir):
    session = chat_mod.ChatSession(db)
    project = session.create_project("product promo animation")
    assert project.status == "proposed"
    assert project.source == "chat"
    assert project.concept_is_offline_substitute is True
    # persisted in the store
    got = db.get_project(project.project_id)
    assert got is not None
    assert got.status == "proposed"
    assert got.source == "chat"
    # a sensitive approval was recorded
    approvals = db.get_approvals(project.project_id)
    assert any(a.kind == "sensitive" for a in approvals)
    # chat history recorded (user requirement + assistant concept)
    msgs = db.get_chat_messages(project.project_id)
    assert len(msgs) >= 2


def test_propose_delegates_to_build_proposal(db):
    session = chat_mod.ChatSession(db)
    p = session.propose("make a trailer", pipeline_override="cinematic")
    assert p.pipeline_type == "cinematic"
    assert p.is_offline_substitute is True
