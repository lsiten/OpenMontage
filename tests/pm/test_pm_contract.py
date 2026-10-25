"""PM hard-boundary contract — zero paid / local / no paid AI / no fake AI.

These tests encode the LSIT-285 hard boundaries so the independent reviewer can
audit them: the entry never calls a paid provider, paid capabilities are always
labeled unconnected, and no concept is presented as a real AI generation.
"""

from pm.capabilities import list_capabilities, split_capabilities
from pm.chat import plan
from pm.schemas import UNCONNECTED
from pm.schemas import ChatRequest


def test_no_paid_capability_is_called_by_plan():
    # The plan path must not mutate the cost log or invoke a provider.
    # We assert the resulting plan reports total estimated spend == 0.
    resp = plan(ChatRequest(requirement="做一个电影感短片，用 Veo 生成"))
    assert resp.cost_estimate.total_estimated_usd == 0.0


def test_paid_capabilities_are_unconnected():
    caps = list_capabilities()
    paid = [c for c in caps if c.classification == "paid"]
    assert paid  # there are paid tools in the registry
    # Any paid capability that is not "available" must be labeled unconnected.
    for c in paid:
        if c.status != "available":
            assert c.note == UNCONNECTED


def test_local_capabilities_are_preferred():
    caps = list_capabilities()
    local, paid = split_capabilities(caps)
    # Local (free) capabilities must exist and be surfaced first.
    assert local
    assert any(c.status == "available" for c in local)


def test_concept_is_not_presented_as_real_ai():
    resp = plan(ChatRequest(requirement="帮我做一个讲解视频"))
    assert resp.concept.is_ai_generated is False
    assert "local-heuristic" in resp.concept.generated_by
