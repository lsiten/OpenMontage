"""Deterministic pipeline-selection tests (Rule Zero, no LLM)."""

from __future__ import annotations

from pm import pipeline_select as sel


def test_all_13_known_pipelines():
    assert len(sel.KNOWN_PIPELINES) == 13


def test_deterministic():
    a = sel.select_pipeline("make a tutorial explainer about how to install python")
    b = sel.select_pipeline("make a tutorial explainer about how to install python")
    assert a.pipeline_type == b.pipeline_type
    assert a.confidence == b.confidence


def test_keyword_hit_cinematic():
    s = sel.select_pipeline("a cinematic short film trailer for a sci-fi movie")
    assert s.pipeline_type == "cinematic"
    assert s.confidence > 0


def test_keyword_hit_podcast():
    s = sel.select_pipeline("repurpose a podcast interview into short clips")
    assert s.pipeline_type in ("podcast-repurpose", "clip-factory")


def test_confidence_capped_below_one():
    for req in ("cinematic film", "podcast", "explainer tutorial"):
        s = sel.select_pipeline(req)
        assert s.confidence <= 1.0


def test_no_signal_fallback():
    s = sel.select_pipeline("zzz xqw xqw zzz")
    assert s.pipeline_type == "animated-explainer"
    assert s.confidence > 0
    assert s.confidence < 0.3
