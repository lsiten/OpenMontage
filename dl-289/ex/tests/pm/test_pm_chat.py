"""PM dialog-entry tests — plan() + trigger() honor the zero-paid boundary."""

from pm import store
from pm.chat import plan, trigger
from pm.schemas import ChatRequest, TriggerRequest


def test_plan_selects_pipeline_and_classifies_cost():
    resp = plan(ChatRequest(requirement="帮我做一个关于黑洞的 60 秒科普讲解视频"))
    assert resp.pipeline_type == "animated-explainer"
    assert resp.confidence > 0
    # Zero-paid boundary: nothing is called, so estimated spend is 0.
    assert resp.cost_estimate.total_estimated_usd == 0.0
    assert len(resp.paid_capabilities) >= 1  # paid rows reported, unconnected
    assert all(c.status != "available" or "不默认调用" in c.note for c in resp.paid_capabilities)
    # Concept is explicitly NOT an AI generation.
    assert resp.concept.is_ai_generated is False


def test_plan_requires_nonempty_brief():
    import pytest

    with pytest.raises(ValueError):
        plan(ChatRequest(requirement="   "))


def test_plan_explicit_pipeline_override():
    resp = plan(ChatRequest(requirement="随便", pipeline_type="screen-demo"))
    assert resp.pipeline_type == "screen-demo"
    assert resp.confidence == 1.0


def test_plan_lists_approval_items():
    resp = plan(ChatRequest(requirement="录一个软件操作演示"))
    # screen-demo has gated stages -> approval items present
    assert resp.approval_items  # non-empty
    kinds = {a.kind for a in resp.approval_items}
    assert "budget" in kinds


def test_trigger_creates_project_without_paid_call():
    resp = plan(ChatRequest(requirement="把这段播客做成短视频"))
    trig = trigger(
        TriggerRequest(
            requirement=resp.requirement,
            pipeline_type=resp.pipeline_type,
            concept=resp.concept.summary,
            cost_budget_usd=resp.cost_estimate.budget_default_usd,
        )
    )
    assert trig.created is True
    got = store.get_project(trig.project_id)
    assert got is not None
    assert got.pipeline_type == resp.pipeline_type
    assert got.status == "draft"
    # The created project must not have called any paid provider: no spend.
    assert got.cost_spent_usd == 0.0
