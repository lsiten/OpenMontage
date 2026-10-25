"""The conversational driver (contract §3) — a local agent, not a real AI.

``pm/chat`` turns a natural-language requirement into a *proposal*: it reuses
the 13-pipeline selection logic (``pipeline_select``), reuses the registry
provider menu (``cost``), and returns
``{pipeline_type, concept, cost_estimate(local/paid), items needing human
approval}`` — exactly the contract's chat-entry output.

Hard boundaries (Agent Identity):
- It does NOT call any paid provider and does NOT impersonate a real AI
  service. The concept it produces is a local template and is labelled an
  offline substitute — never claimed to be a validated real-AI generation.
- It does NOT add an execution engine. "Triggering" only creates the project
  via the PM write layer (``init_project`` + store + project.json ``pm``
  segment) and records the proposal; the actual pipeline run stays with the
  agent (manifest + director skills + registry).
- Any paid capability is named as a human-approval item; it is never run.
- Bloome (README) is a third-party cloud multi-agent chat — external, not
  reused; PM's chat is a self-built local orchestrator.
"""

from __future__ import annotations

import re
from typing import Optional

from pm import cost as cost_mod
from pm import pipeline_select as selector
from pm import schema
from pm.store import PMDatabase

OFFLINE_SUBSTITUTE_BANNER = (
    "[离线替身 / OFFLINE SUBSTITUTE — 不代表真实 AI 服务已接入，生成质量未验收]"
)


def _slugify(text: str, fallback: str = "project") -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:48] or fallback


def _title_from(requirement: str) -> str:
    req = (requirement or "").strip()
    first = req.splitlines()[0] if req else ""
    return first[:60] or "Untitled project"


def generate_concept(requirement: str, pipeline_type: str, selection: schema.PipelineSelection) -> str:
    """A LOCAL template concept. Deterministic, no LLM, no paid call.

    It is explicitly an offline substitute: it structures the brief using the
    selected pipeline's known shape, but it is NOT a validated real-AI
    generation. ``concept_is_offline_substitute`` is always True.
    """
    hook = (requirement or "").strip().splitlines()[0] or "（未提供需求）"
    concept = (
        f"{OFFLINE_SUBSTITUTE_BANNER}\n"
        f"标题: {_title_from(requirement)}\n"
        f"需求: {hook}\n"
        f"管线: {pipeline_type}（置信度 {selection.confidence:.0%}；备选 {selection.alternatives or '—'}）\n"
        f"视觉: 本地/离线运行时优先（Remotion/HyperFrames；TTS 用 Piper；无 GPU 时仅 Remotion/HyperFrames/Piper 可用）\n"
        f"说明: 这是规则生成的离线替身概念，用于立项与审批；真实生成质量未接入/未验收，"
        f"付费 provider 未接入。"
    )
    return concept


def approval_items(cost: schema.CostEstimate, requirement: str) -> list[schema.HumanApprovalItem]:
    """Human-approval items the user must clear before ANY paid call.

    Paid capabilities are never run by PM; they surface here as items the
    user must approve (proposal + cost_tracker.reserve + user confirmation).
    Sensitive content (real voice / portrait / music) is never connected.
    """
    items: list[schema.HumanApprovalItem] = []
    seen: set[str] = set()
    for cap in cost.paid_capabilities:
        if cap.status == "available":
            # Configured but still paid: an explicit approval is required to run.
            kind = "paid_call"
        else:
            kind = "paid_call"
        label = f"{cap.capability} / {cap.provider or cap.tool or '—'}：{cap.status_label}"
        if label in seen:
            continue
        seen.add(label)
        items.append(
            schema.HumanApprovalItem(
                kind=kind,
                label=label,
                reason="付费 provider：未接入/需授权；需 proposal 审批 + cost_tracker.reserve + 用户确认后方可调用。",
            )
        )
    # Sensitive content is never connected — recorded as a hard boundary.
    items.append(
        schema.HumanApprovalItem(
            kind="sensitive",
            label="敏感/真人声音/肖像/音乐：不接入",
            reason="硬约束：PM 不接入敏感、真人声音、肖像或音乐；需用户另行确认。",
        )
    )
    return items


def build_proposal(
    requirement: str,
    registry: Optional[object] = None,
    pipeline_override: str = "",
) -> schema.ProposalPacket:
    """The chat entry's core: requirement -> proposal packet.

    Reuses the pipeline selector (Rule Zero) and the registry provider menu;
    classifies local vs paid cost; names human-approval items. It never
    executes a provider and never impersonates a real AI service.
    """
    requirement = (requirement or "").strip()
    selection = selector.select_pipeline(requirement)
    if pipeline_override and pipeline_override in selector.KNOWN_PIPELINES:
        selection = schema.PipelineSelection(
            pipeline_type=pipeline_override,
            confidence=selection.confidence,
            reason=f"用户指定管线 {pipeline_override}（覆盖自动选择 {selection.pipeline_type}）。",
            alternatives=selection.alternatives,
        )

    cost = cost_mod.estimate_cost(
        pipeline_type=selection.pipeline_type,
        concept="",
        requirement=requirement,
        registry=registry,
    )
    concept = generate_concept(requirement, selection.pipeline_type, selection)
    items = approval_items(cost, requirement)
    note = "本地/离线能力优先；付费 provider 仅分类不接入。本提案由 pm/chat 规则生成，未调用任何真实/付费 AI。"

    return schema.ProposalPacket(
        requirement=requirement,
        pipeline_type=selection.pipeline_type,
        selection=selection,
        concept=concept,
        cost_estimate=cost,
        human_approval_items=items,
        is_offline_substitute=True,
        note=note,
    )


class ChatSession:
    """A conversational session bound to (or creating) one PM project.

    It stores the proposal and chat history, and can "trigger" by creating
    the project through the PM write layer. Triggering does NOT run the
    pipeline or any paid provider — it only creates the project in the
    ``proposed`` state, ready for the agent to drive.
    """

    def __init__(self, store: PMDatabase, db_path: Optional[object] = None) -> None:
        self.store = store

    def propose(self, requirement: str, pipeline_override: str = "") -> schema.ProposalPacket:
        return build_proposal(requirement, pipeline_override=pipeline_override)

    def create_project(self, requirement: str, pipeline_override: str = "") -> schema.PmProject:
        """Trigger: create the project via the PM write layer.

        Uses ``init_project`` (the canonical layout the pipeline also uses)
        and persists PM metadata. Does NOT start the pipeline and does NOT
        call any paid provider.
        """
        proposal = self.build(requirement, pipeline_override=pipeline_override)
        project_id = _slugify(proposal.requirement) or "project"
        title = _title_from(proposal.requirement)

        # 1) create the on-disk project directory (canonical layout) — the
        #    PM write layer owns this; it is NOT a Backlot read-only file.
        try:
            from lib.checkpoint import init_project
            init_project(
                project_id,
                title=title,
                pipeline_type=proposal.pipeline_type,
            )
        except Exception:
            pass  # degrade: the SQLite record still records the project.

        # 2) persist PM metadata.
        project = schema.PmProject(
            project_id=project_id,
            title=title,
            requirement=proposal.requirement,
            pipeline_type=proposal.pipeline_type,
            concept=proposal.concept,
            concept_is_offline_substitute=True,
            status="proposed",
            cost_budget_usd=10.0,
            source="chat",
            cost_estimate=proposal.cost_estimate,
        )
        self.store.upsert_project(project)
        # 3) record the proposal as a chat message + a human-approval request.
        self.store.add_chat_message(project_id, "user", proposal.requirement)
        self.store.add_chat_message(project_id, "assistant", proposal.concept)
        for item in proposal.human_approval_items:
            self.store.add_approval(
                schema.Approval(
                    project_id=project_id,
                    stage="",
                    kind=item.kind,
                    status="pending",
                    note=item.label,
                )
            )
        # 4) mirror the pm segment into project.json (defensive; see state.py).
        try:
            from pm import state as state_mod
            state_mod.write_pm_segment(project_id, project)
        except Exception:
            pass
        return project

    def build(self, requirement: str, pipeline_override: str = "") -> schema.ProposalPacket:
        return build_proposal(requirement, pipeline_override=pipeline_override)
