"""Typed contracts for the PM writable layer (pydantic v2 + jsonschema).

Two validation layers, both offline:
  * pydantic v2 models — the app's runtime types (FastAPI request/response).
  * a JSON-Schema (Draft 2020-12) — the on-disk contract for the ``pm``
    segment written into ``projects/<id>/project.json`` and the rows PM
    persists in SQLite. This keeps the stored metadata machine-checkable
    without a third-party DB dependency.

Nothing here calls a paid service or a real AI. It is pure data shape.
"""

from __future__ import annotations

from typing import Literal, Optional

import jsonschema
from pydantic import BaseModel, Field, field_validator

# --- Status / mode vocabularies -------------------------------------------

# PM project lifecycle. Distinct from Backlot's stage status: this is the
# whole-project PM view, not a single pipeline stage.
ProjectStatus = Literal[
    "draft",          # created, not yet approved / started
    "proposed",       # a proposal packet exists (awaiting human approval)
    "in_progress",    # the pipeline is being driven by the agent
    "blocked",        # a human approval / budget gate is holding it
    "done",           # render artifact delivered
    "cancelled",
]

ApprovalStatus = Literal["pending", "approved", "rejected"]
# Cost entry lifecycle mirrors tools/cost_tracker.EntryStatus so PM and the
# pipeline cost tracker stay in the same vocabulary.
CostEntryStatus = Literal["estimated", "reserved", "completed", "failed", "refunded"]
# Where the metadata came from — the conversational driver vs. the CLI/manual
# create path. Recorded so the board can show "this came from pm/chat".
Source = Literal["chat", "cli", "manual", "api"]


class BudgetMode(BaseModel):
    """Echo of lib.config_model.BudgetMode, kept dependency-light on purpose."""

    mode: Literal["observe", "warn", "cap"] = "warn"
    total_usd: float = Field(default=10.0, ge=0)
    single_action_approval_usd: float = Field(default=0.50, ge=0)


# --- Capability / cost classification ------------------------------------

class CapabilityEntry(BaseModel):
    """One provider/capability cell of the provider menu, classified local|paid."""

    capability: str
    provider: str
    tool: Optional[str] = None
    runtime: str = "unknown"          # ToolRuntime: local / local_gpu / api / hybrid
    status: str = "unavailable"       # ToolStatus: available / unavailable / degraded
    is_local: bool = False            # runs offline, zero key, no paid call
    is_paid: bool = False             # needs a paid API key / cloud service
    best_for: str = ""
    status_label: str = "未接入/需授权"  # human-facing; Simplified Chinese
    install_instructions: str = ""


class CostEstimate(BaseModel):
    """Local-vs-paid cost split. ``paid_usd`` is a *classification*, never a
    reservation — no paid provider is ever called by PM."""

    total_local_usd: float = Field(default=0.0, ge=0)
    total_paid_usd: float = Field(default=0.0, ge=0)
    local_capabilities: list[CapabilityEntry] = Field(default_factory=list)
    paid_capabilities: list[CapabilityEntry] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


# --- Pipeline selection (Q3: reuse the 13 agentic pipelines) -------------

class PipelineSelection(BaseModel):
    """The rule-based 'pipeline selection' the chat driver reuses.

    This is deliberately NOT an LLM: it is a deterministic matcher over the
    13 pipeline manifests (Rule Zero — every video request is a pipeline
    selection question). ``alternatives`` are the runner-ups the agent would
    also consider.
    """

    pipeline_type: str
    confidence: float = Field(default=0.0, ge=0, le=1)
    reason: str = ""
    alternatives: list[str] = Field(default_factory=list)


# --- Project metadata (the writable layer) -------------------------------

class PmProject(BaseModel):
    """A PM-managed project. Keyed by ``project_id`` and associated with the
    on-disk ``projects/<id>/`` directory of the same name."""

    project_id: str
    title: str = ""
    requirement: str = ""             # the natural-language brief
    pipeline_type: str = "unknown"
    concept: str = ""                # a LOCAL template concept (offline substitute)
    status: ProjectStatus = "draft"
    mode: BudgetMode = Field(default_factory=BudgetMode)
    cost_budget_usd: float = Field(default=10.0, ge=0)
    cost_estimate: Optional[CostEstimate] = None
    source: Source = "manual"
    created_at: str = ""
    updated_at: str = ""
    # The offline-substitute flag is the hard constraint made explicit: a
    # PM-generated concept is never claimed to be a validated real AI output.
    concept_is_offline_substitute: bool = True


class ProjectCreate(BaseModel):
    requirement: str = ""
    title: str = ""
    pipeline_type: str = ""          # empty => let the selector choose
    cost_budget_usd: float = Field(default=10.0, ge=0)
    mode: BudgetMode = Field(default_factory=BudgetMode)
    source: Source = "manual"

    @field_validator("requirement")
    @classmethod
    def _strip(cls, v: str) -> str:
        return (v or "").strip()


class ProjectUpdate(BaseModel):
    title: Optional[str] = None
    requirement: Optional[str] = None
    pipeline_type: Optional[str] = None
    concept: Optional[str] = None
    status: Optional[ProjectStatus] = None
    cost_budget_usd: Optional[float] = Field(default=None, ge=0)
    mode: Optional[BudgetMode] = None


class Approval(BaseModel):
    entry_id: str = ""
    project_id: str
    stage: str = ""
    kind: str = "paid_call"        # paid_call / new_paid_tool / sensitive / budget
    requested_at: str = ""
    status: ApprovalStatus = "pending"
    decided_at: str = ""
    decided_by: str = ""
    note: str = ""


class CostEntry(BaseModel):
    project_id: str
    entry_id: str
    tool: str = ""
    operation: str = ""
    estimated_usd: float = Field(default=0.0, ge=0)
    reserved_usd: float = Field(default=0.0, ge=0)
    actual_usd: float = Field(default=0.0, ge=0)
    status: CostEntryStatus = "estimated"
    is_paid: bool = False
    created_at: str = ""


class HumanApprovalItem(BaseModel):
    kind: str                       # paid_call / new_paid_tool / sensitive / budget
    label: str                      # human-facing description (Simplified Chinese)
    reason: str = ""


# --- Chat / proposal (Q3 contract) --------------------------------------

class ProposalPacket(BaseModel):
    """The output of the conversational driver.

    Per the contract (§3): input = a natural-language requirement; output =
    ``{pipeline_type, concept, cost_estimate(local/paid), items needing human
    approval}``. It is a *proposal*, not an execution: triggering creates the
    project (PM write layer) but does NOT run any paid provider.
    """

    requirement: str
    pipeline_type: str
    selection: PipelineSelection
    concept: str
    cost_estimate: CostEstimate
    human_approval_items: list[HumanApprovalItem] = Field(default_factory=list)
    # Hard constraint made explicit (Agent Identity): an offline/placeholder
    # concept is never claimed to be a real, validated AI generation.
    is_offline_substitute: bool = True
    note: str = ""


# --- JSON Schema for the persisted ``pm`` segment ------------------------
#
# The ``pm`` segment written into project.json and the shape of the SQLite
# rows. Kept as a plain Draft 2020-12 document so it can be validated with
# jsonschema without importing pydantic at the boundary.

PM_PROJECT_JSON_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "PM project segment",
    "type": "object",
    "additionalProperties": True,
    "required": ["project_id", "status"],
    "properties": {
        "project_id": {"type": "string"},
        "title": {"type": "string"},
        "requirement": {"type": "string"},
        "pipeline_type": {"type": "string"},
        "concept": {"type": "string"},
        "concept_is_offline_substitute": {"type": "boolean"},
        "status": {"type": "string", "enum": ["draft", "proposed", "in_progress", "blocked", "done", "cancelled"]},
        "cost_budget_usd": {"type": "number", "minimum": 0},
        "source": {"type": "string", "enum": ["chat", "cli", "manual", "api"]},
        "created_at": {"type": "string"},
        "updated_at": {"type": "string"},
    },
}


def validate_pm_segment(segment: dict) -> None:
    """Raise jsonschema.ValidationError if ``segment`` is not a valid PM segment."""
    jsonschema.validate(instance=segment, schema=PM_PROJECT_JSON_SCHEMA)
