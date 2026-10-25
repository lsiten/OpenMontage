"""Pydantic v2 models for the PM contract.

These are the wire shapes for the two capabilities from the LSIT-285 contract:
  (1) PM application: create / read / update / status / cost / approval.
  (2) Dialog-driven entry: brief -> {pipeline_type, concept, cost_estimate,
      human-approval-items}.

All are strict (extra="forbid") so the contract is auditable by the independent
reviewer: a request that carries paid-service knobs is rejected, not silently
ignored.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

# Project lifecycle. Mirrors the pipeline stage rail's human-approval semantics
# but is a *PM metadata* state, not a checkpoint status.
ProjectStatus = Literal[
    "draft",        # created, not yet planned
    "planning",     # brief accepted; proposal/plan formed, awaiting approval
    "approved",     # budget + plan approved by a human
    "running",      # agent-driven pipeline execution in progress
    "paused",       # budget gate / blocker paused execution
    "completed",    # pipeline finished
    "cancelled",    # human cancelled
    "failed",       # execution failed
]

CostMode = Literal["observe", "warn", "cap"]

UNCONNECTED = "未接入/需授权"  # "not connected / requires authorization"


class CapabilityInfo(BaseModel):
    """One capability row, classified local vs paid by runtime."""

    capability: str
    tool: str
    provider: str
    runtime: str  # local | local_gpu | api | hybrid
    classification: Literal["local", "paid"]
    status: str  # available | unavailable | degraded
    note: str = ""


class CostEstimate(BaseModel):
    """Local/paid classification of a plan's cost — never a live spend.

    ``total_estimated_usd`` is 0.0 for any plan that does not call a paid
    provider (the hard zero-paid boundary). Paid rows are always classified
    ``UNCONNECTED`` and are never actually invoked.
    """

    currency: str = "usd"
    total_estimated_usd: float = 0.0
    budget_default_usd: float = 0.0
    reserve_usd: float = 0.0
    local: list[CapabilityInfo] = Field(default_factory=list)
    paid: list[CapabilityInfo] = Field(default_factory=list)
    note: str = (
        "本地/离线能力优先；付费能力显示为未接入/需授权，不默认调用。"
        "Offline/local capabilities first; paid capabilities are shown as "
        "unconnected and are never called by default."
    )


class ApprovalItem(BaseModel):
    kind: str  # budget | new_paid_tool | publish | stage:<name>
    detail: str


class Concept(BaseModel):
    """A deterministic, local, template-derived concept draft.

    Explicitly NOT an LLM/AI generation. It is assembled from the brief, the
    selected pipeline, and the available local capabilities, and is labeled as
    an unverified draft so it is never mistaken for a real AI service.
    """

    summary: str
    visual_approach: str
    narrative: str
    is_ai_generated: bool = False
    generated_by: str = "local-heuristic (not an AI service)"


# --- PM application (CRUD) -------------------------------------------------

class ProjectCreate(BaseModel):
    title: str
    pipeline_type: str
    concept: Optional[str] = None
    render_runtime: Optional[str] = None
    cost_budget_usd: float = Field(default=0.0, ge=0.0)
    cost_mode: CostMode = "warn"
    requires_approval: bool = True
    requirement: Optional[str] = None
    created_by: Optional[str] = None
    notes: Optional[str] = None


class ProjectUpdate(BaseModel):
    status: Optional[ProjectStatus] = None
    cost_budget_usd: Optional[float] = Field(default=None, ge=0.0)
    cost_mode: Optional[CostMode] = None
    approved: Optional[bool] = None
    notes: Optional[str] = None
    updated_by: Optional[str] = None


class ProjectResponse(BaseModel):
    project_id: str
    title: str
    pipeline_type: str
    concept: Optional[str] = None
    status: ProjectStatus
    render_runtime: Optional[str] = None
    cost_budget_usd: float
    cost_reserved_usd: float
    cost_spent_usd: float
    cost_mode: CostMode
    requires_approval: bool
    approved: bool
    requirement: Optional[str] = None
    created_by: Optional[str] = None
    notes: Optional[str] = None
    created_at: str
    updated_at: str


class ApprovalRequest(BaseModel):
    kind: str
    detail: Optional[str] = None
    requested_by: Optional[str] = None


class ApprovalDecision(BaseModel):
    status: Literal["approved", "rejected"]
    decided_by: Optional[str] = None
    note: Optional[str] = None


class ApprovalResponse(BaseModel):
    id: int
    project_id: str
    kind: str
    detail: Optional[str] = None
    status: str
    requested_by: Optional[str] = None
    decided_by: Optional[str] = None
    created_at: str
    decided_at: Optional[str] = None


# --- Dialog-driven entry ---------------------------------------------------

class ChatRequest(BaseModel):
    requirement: str
    # Optional human steering; all optional so a bare brief is valid.
    pipeline_type: Optional[str] = None
    budget_usd: Optional[float] = Field(default=None, ge=0.0)
    cost_mode: Optional[CostMode] = None


class ChatResponse(BaseModel):
    requirement: str
    pipeline_type: str
    confidence: float = 0.0
    candidates: list[dict] = Field(default_factory=list)
    concept: Concept
    cost_estimate: CostEstimate
    approval_items: list[ApprovalItem] = Field(default_factory=list)
    local_capabilities: list[CapabilityInfo] = Field(default_factory=list)
    paid_capabilities: list[CapabilityInfo] = Field(default_factory=list)
    can_trigger: bool = True
    note: str = (
        "本地对话入口：把需求→管线选择→概念/成本提案。不直接调用付费 provider；"
        "任何付费调用仍需 proposal 审批 + cost_tracker.reserve + 用户确认。"
        "Local dialog entry; never calls a paid provider directly."
    )


class TriggerRequest(BaseModel):
    """Turn an accepted ChatResponse into a persisted project record.

    Carries only the plan fields; it never carries a live provider call.
    """

    requirement: str
    pipeline_type: str
    concept: Optional[str] = None
    render_runtime: Optional[str] = None
    cost_budget_usd: Optional[float] = Field(default=None, ge=0.0)
    cost_mode: Optional[CostMode] = None
    created_by: Optional[str] = None
    approved: bool = False


class TriggerResponse(BaseModel):
    project_id: str
    title: str
    pipeline_type: str
    status: ProjectStatus
    created: bool = True
    note: str = (
        "已创建 PM 项目记录（写层）。未启动/未调用付费 provider；管线由 agent 驱动。"
        "PM record created. No paid provider was called; the pipeline is "
        "agent-driven, not invoked here."
    )
