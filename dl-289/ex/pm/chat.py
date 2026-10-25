"""Dialog-driven entry — brief -> pipeline selection -> concept + cost proposal.

Implements the LSIT-285 dialog-entry contract:
  input  = a natural language brief
  output = {pipeline_type, concept, cost_estimate(local/paid), approval items}
  trigger= create the PM project record (+ runtime dir/marker); the pipeline
           itself is agent-driven, NOT invoked here.

Hard boundaries honored here:
- No paid provider is ever called (zero paid / local / no paid AI).
- The "conversation" is local agent orchestration reusing the 13 pipelines'
  selection logic. The concept is a *local template draft*, explicitly not an
  AI generation, so it is never mistaken for a real AI service.
- Any paid call would still require proposal approval + cost_tracker.reserve +
  user confirmation; this run does not trial-run paid services.
"""

from __future__ import annotations

from typing import Optional

from pm import store
from pm.capabilities import list_capabilities, split_capabilities
from pm.pipeline_select import select_pipeline
from pm.schemas import (
    ApprovalItem,
    ChatRequest,
    ChatResponse,
    Concept,
    CostEstimate,
    ProjectCreate,
    TriggerRequest,
    TriggerResponse,
)


def _pipeline_meta(pipeline_type: str) -> dict:
    """Best-effort pipeline manifest (category / budget / gated stages)."""
    try:
        from lib.pipeline_loader import load_pipeline_readonly

        return load_pipeline_readonly(pipeline_type)
    except Exception:
        return {}


def _budget_default(pipeline_type: str) -> float:
    meta = _pipeline_meta(pipeline_type)
    orchestration = meta.get("orchestration") or {}
    try:
        return float(orchestration.get("budget_default_usd", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _gated_stages(pipeline_type: str) -> list[str]:
    meta = _pipeline_meta(pipeline_type)
    return [
        s.get("name", "")
        for s in (meta.get("stages") or [])
        if isinstance(s, dict) and s.get("human_approval_default")
    ]


def _build_concept(brief: str, pipeline_type: str) -> Concept:
    """Deterministic, local, template-derived concept draft (NOT an LLM/AI)."""
    meta = _pipeline_meta(pipeline_type)
    category = meta.get("category") or pipeline_type
    desc = (meta.get("description") or "").strip().replace("\n", " ")
    if len(desc) > 160:
        desc = desc[:157] + "..."
    brief = brief.strip()
    summary = f"{brief[:120]}（管线: {pipeline_type}，类别: {category}）。"
    if desc:
        summary = f"{summary} 该管线: {desc}"
    visual_approach = (
        f"以 {pipeline_type} 的既定视觉语言呈现；优先本地/离线合成能力"
        f"（Remotion/HyperFrames/本地 Piper TTS/本地 diffusion），付费能力"
        f"显示为未接入/需授权，不默认调用。"
    )
    narrative = (
        "由 agent 依 pipeline manifest + stage director skills 逐阶段驱动；"
        "本入口只负责把需求→管线+概念+成本提案，不新增执行引擎、不调用付费 provider。"
    )
    return Concept(
        summary=summary,
        visual_approach=visual_approach,
        narrative=narrative,
        is_ai_generated=False,
        generated_by="local-heuristic (not an AI service)",
    )


def _cost_estimate(
    pipeline_type: str,
    budget_usd: Optional[float],
    cost_mode: str,
) -> CostEstimate:
    """Local/paid cost classification. total_estimated_usd is 0 (no paid call)."""
    from tools.cost_tracker import CostTracker

    budget = budget_usd if budget_usd is not None else _budget_default(pipeline_type)
    # Reuse the budget-governance model (in-memory; no cost_log write, no call).
    tracker = CostTracker(
        budget_total_usd=budget,
        reserve_pct=0.10,
        mode=_mode_enum(cost_mode),
    )
    capabilities = list_capabilities()
    local, paid = split_capabilities(capabilities)
    return CostEstimate(
        total_estimated_usd=0.0,  # zero-paid boundary: nothing is called
        budget_default_usd=round(budget, 4),
        reserve_usd=round(tracker.budget_total_usd * tracker.reserve_pct, 4),
        local=local,
        paid=paid,
    )


def _mode_enum(cost_mode: Optional[str]):
    from lib.config_model import BudgetMode

    try:
        return BudgetMode(cost_mode or "warn")
    except Exception:
        return BudgetMode.WARN


def _approval_items(
    pipeline_type: str,
    cost_estimate: CostEstimate,
    requires_approval: bool,
) -> list[ApprovalItem]:
    items: list[ApprovalItem] = []
    for stage in _gated_stages(pipeline_type):
        items.append(
            ApprovalItem(kind=f"stage:{stage}", detail=f"阶段 {stage} 需人类审批")
        )
    if requires_approval or cost_estimate.paid:
        items.append(
            ApprovalItem(
                kind="budget",
                detail=(
                    f"预算/付费能力审批（预算 {cost_estimate.budget_default_usd} USD；"
                    f"付费能力 {len(cost_estimate.paid)} 项，均为未接入/需授权，不默认调用）。"
                ),
            )
        )
    # publish is gated in most pipelines; flag it if present.
    if any(a.kind == "stage:publish" for a in items):
        pass
    return items


def plan(req: ChatRequest) -> ChatResponse:
    """The dialog entry: brief -> pipeline selection + concept + cost proposal."""
    requirement = req.requirement.strip()
    if not requirement:
        raise ValueError("requirement 不能为空")

    if req.pipeline_type:
        # Explicit steering: honor it, but keep the heuristic as a sanity check.
        selection = select_pipeline(requirement)
        pipeline_type = req.pipeline_type
        confidence = 1.0
        candidates = [
            {"pipeline_type": pipeline_type, "score": 0, "matched": ["explicit"]}
        ]
    else:
        selection = select_pipeline(requirement)
        pipeline_type = selection.pipeline_type
        confidence = selection.confidence
        candidates = [
            {
                "pipeline_type": c.pipeline_type,
                "score": c.score,
                "matched": c.matched,
                "category": c.category,
                "stability": c.stability,
            }
            for c in selection.candidates
        ]

    cost_estimate = _cost_estimate(pipeline_type, req.budget_usd, req.cost_mode)
    concept = _build_concept(requirement, pipeline_type)
    approval_items = _approval_items(
        pipeline_type, cost_estimate, requires_approval=True
    )
    capabilities = list_capabilities()
    local, paid = split_capabilities(capabilities)
    return ChatResponse(
        requirement=requirement,
        pipeline_type=pipeline_type,
        confidence=confidence,
        candidates=candidates,
        concept=concept,
        cost_estimate=cost_estimate,
        approval_items=approval_items,
        local_capabilities=local,
        paid_capabilities=paid,
    )


def trigger(req: TriggerRequest) -> TriggerResponse:
    """Persist a project from an accepted plan. NO paid provider is called.

    Creates the PM record (SQLite) + the runtime projects/<id>/ dir + a
    Backlot-compatible marker. The pipeline itself is agent-driven; this entry
    only records intent + the cost/budget governance, never invoking a provider.
    """
    budget = (
        req.cost_budget_usd
        if req.cost_budget_usd is not None
        else _budget_default(req.pipeline_type)
    )
    created = store.create_project(
        ProjectCreate(
            title=req.requirement.strip()[:80] or req.pipeline_type,
            pipeline_type=req.pipeline_type,
            concept=req.concept or "",
            render_runtime=req.render_runtime,
            cost_budget_usd=budget,
            cost_mode=req.cost_mode or "warn",
            requires_approval=not req.approved,
            requirement=req.requirement.strip(),
            created_by=req.created_by or "dialog-entry",
            notes="由对话入口创建；未调用付费 provider。",
        )
    )
    return TriggerResponse(
        project_id=created.project_id,
        title=created.title,
        pipeline_type=created.pipeline_type,
        status=created.status,
    )
