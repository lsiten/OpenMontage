"""Cost classification tests (the zero-paid boundary).

PM never calls a paid provider; it only *classifies* capability cells as
local/offline vs paid/needs-auth and names the paid ones as "未接入/需授权".
These tests use a deterministic fake registry so they never depend on the
real tool registry, plus one guard against the real registry too.
"""

from __future__ import annotations

from pm import cost as cost_mod


class _FakeRegistry:
    """A deterministic provider menu for classification assertions."""

    def provider_menu(self):
        return {
            "video_generation": {
                "available": [
                    {"name": "remotion", "provider": "remotion", "runtime": "local",
                     "status": "available", "best_for": ["local render", "x"]},
                ],
                "unavailable": [
                    {"name": "veo", "provider": "veo", "runtime": "api",
                     "status": "unavailable", "best_for": "cloud video"},
                ],
            },
            "tts": {
                "available": [
                    {"name": "piper", "provider": "piper", "runtime": "local",
                     "status": "available", "best_for": ["tts"]},
                ],
                "unavailable": [],
            },
            "music": {
                "available": [],
                "unavailable": [
                    {"name": "suno", "provider": "suno", "runtime": "api",
                     "status": "unavailable", "best_for": ["music"]},
                ],
            },
        }


def test_classify_api_is_paid_and_unconfigured():
    e = cost_mod.classify_entry(
        {"name": "veo", "provider": "veo", "runtime": "api",
         "status": "unavailable", "best_for": "x"}, "video_generation"
    )
    assert e.is_paid is True
    assert e.is_local is False
    assert e.status_label == cost_mod.STATUS_LABEL_UNCONFIGURED


def test_classify_local_is_local():
    e = cost_mod.classify_entry(
        {"name": "remotion", "provider": "remotion", "runtime": "local",
         "status": "available", "best_for": ["a", "b"]}, "video_generation"
    )
    assert e.is_local is True
    assert e.is_paid is False
    assert e.status_label == cost_mod.STATUS_LABEL_LOCAL
    # best_for was a list -> normalized to text (regression guard).
    assert e.best_for == "a / b"
    assert isinstance(e.best_for, str)


def test_classify_local_gpu_is_local_but_needs_gpu():
    e = cost_mod.classify_entry(
        {"name": "comfyui", "provider": "comfyui", "runtime": "local_gpu",
         "status": "available", "best_for": "x"}, "image_generation"
    )
    assert e.is_local is True
    assert e.is_paid is False
    assert e.status_label == cost_mod.STATUS_LABEL_LOCAL_GPU


def test_named_paid_provider_overrides_local_runtime():
    # A local runtime but a named paid provider must still classify as paid.
    e = cost_mod.classify_entry(
        {"name": "gemini_video", "provider": "gemini", "runtime": "local",
         "status": "available", "best_for": "x"}, "video_generation"
    )
    assert e.is_paid is True
    assert e.is_local is False


def test_build_capability_report_local_paid_split():
    rep = cost_mod.build_capability_report(_FakeRegistry())
    s = rep["summary"]
    assert s["local"] == 2
    assert s["paid"] == 2
    assert s["unconfigured_paid"] == 2
    assert s["capabilities"] == ["music", "tts", "video_generation"]
    for c in rep["paid"]:
        assert c.is_paid is True
        assert c.status_label == cost_mod.STATUS_LABEL_UNCONFIGURED
    for c in rep["local"]:
        assert c.is_local is True
        assert c.is_paid is False


def test_estimate_cost_zero_paid_boundary():
    est = cost_mod.estimate_cost("cinematic", registry=_FakeRegistry())
    assert est.total_paid_usd == 0.0
    assert est.total_local_usd == 0.0
    assert est.paid_capabilities  # named, never run
    assert est.local_capabilities


def test_estimate_cost_zero_paid_against_real_registry():
    # The real registry must also never produce a paid dollar figure.
    est = cost_mod.estimate_cost("talking-head", registry=None)
    assert est.total_paid_usd == 0.0
