"""Schema + JSON-Schema validation tests."""

from __future__ import annotations

import jsonschema
import pytest
from pm import schema


def test_pmproject_defaults():
    p = schema.PmProject(project_id="x")
    assert p.status == "draft"
    assert p.concept_is_offline_substitute is True
    assert p.source == "manual"


def test_cost_estimate_paid_default_zero():
    ce = schema.CostEstimate()
    assert ce.total_paid_usd == 0.0
    assert ce.total_local_usd == 0.0


def test_budget_mode_validation():
    with pytest.raises(Exception):
        schema.BudgetMode(mode="cap", total_usd=-1.0)  # ge=0


def test_jsonschema_accepts_valid_segment():
    seg = {"project_id": "p1", "status": "draft", "source": "chat"}
    schema.validate_pm_segment(seg)  # no raise


def test_jsonschema_rejects_bad_status():
    with pytest.raises(jsonschema.ValidationError):
        schema.validate_pm_segment({"project_id": "p1", "status": "not-a-status"})


def test_jsonschema_requires_status():
    with pytest.raises(jsonschema.ValidationError):
        schema.validate_pm_segment({"project_id": "p1"})


def test_proposal_is_offline_substitute_by_default():
    p = schema.ProposalPacket(requirement="r", pipeline_type="cinematic",
                              selection=schema.PipelineSelection(pipeline_type="cinematic"),
                              concept="c", cost_estimate=schema.CostEstimate())
    assert p.is_offline_substitute is True
