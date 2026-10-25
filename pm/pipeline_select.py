"""Deterministic pipeline selection — the logic the chat driver reuses.

This is the "pipeline selection" half of the conversational driver (contract
§3). It is Rule Zero made into code: every video request is treated as a
pipeline selection question. It is deliberately NOT an LLM — a rule-based
matcher over the 13 agentic pipeline manifests. It reuses the manifest
descriptions so it stays grounded, and falls back to a keyword map if a
manifest can't be loaded.

Honesty contract: the ``confidence`` is a transparent match score, not a
trained probability. ``reason`` names the matched signals. This is the
"agent-driven, no new execution engine" boundary — selection only; execution
stays with the agent (manifest + director skills + registry).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from pm import schema

PIPELINES_DIR = Path(__file__).resolve().parent.parent / "pipeline_defs"

# The 13 agentic pipelines (contract §0, confirmed). Order matters only for
# tie-breaking / display.
KNOWN_PIPELINES = [
    "animated-explainer", "animation", "avatar-spokesperson", "character-animation",
    "cinematic", "clip-factory", "documentary-montage", "framework-smoke",
    "hybrid", "localization-dub", "podcast-repurpose", "screen-demo", "talking-head",
]

# Keyword signals per pipeline. These are matched against a lower-cased,
# de-punctuated requirement. They are heuristics, not a trained model.
KEYWORDS: dict[str, list[str]] = {
    "animated-explainer": [
        "explainer", "explain", "tutorial", "how to", "how-to", "concept", "data",
        "statistics", "stats", "numbers", "infographic", "pitch", "educational",
        "learn", "teach", "overview", "summary",
    ],
    "animation": [
        "animation", "animate", "motion", "motion graphics", "2d", "illustration",
        "draw", "drawing", "kinetic",
    ],
    "avatar-spokesperson": [
        "avatar", "spokesperson", "presenter", "digital human", "virtual host",
        "talking avatar", "ai presenter", "brand voice",
    ],
    "character-animation": [
        "character", "rigged", "cartoon", "character animation", "pose", "rig",
        "animated character", "mascot",
    ],
    "cinematic": [
        "cinematic", "film", "movie", "short film", "trailer", "drama", "narrative",
        "story", "scene", "blockbuster", "epic",
    ],
    "clip-factory": [
        "clip", "batch", "shorts", "short-form", "short form", "reel", "reels",
        "many clips", "multiple clips", "series", "viral clips",
    ],
    "documentary-montage": [
        "documentary", "montage", "footage", "source media", "edit footage",
        "b-roll", "broll", "real footage", "news",
    ],
    "framework-smoke": [
        "framework", "smoke", "smoke test", "proof of concept", "poc", "demo",
        "sanity", "test the pipeline",
    ],
    "hybrid": [
        "hybrid", "mixed", "combination", "combines", "both", "real and generated",
        "stock and ai", "mix",
    ],
    "localization-dub": [
        "dub", "dubbing", "localize", "localization", "localise", "translate",
        "translation", "subtitles", "multilingual", "regional", "version for",
    ],
    "podcast-repurpose": [
        "podcast", "repurpose", "audio to video", "audio-to-video", "interview",
        "conversation", "dialogue", "audio clip",
    ],
    "screen-demo": [
        "screen", "screen demo", "screen recording", "app demo", "software demo",
        "ui walkthrough", "product demo", "app tutorial", "interface",
    ],
    "talking-head": [
        "talking head", "talking-head", "talking", "face to camera", "presenter",
        "on camera", "on-camera", "host",
    ],
}


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower()).strip()


def _load_descriptions() -> dict[str, str]:
    """Best-effort manifest descriptions; degrade to '' on any failure."""
    out: dict[str, str] = {}
    try:
        from lib.pipeline_loader import load_pipeline
    except Exception:
        return out
    for name in KNOWN_PIPELINES:
        try:
            manifest = load_pipeline(name)
            out[name] = _normalize(str(manifest.get("description") or ""))
        except Exception:
            out[name] = ""
    return out


def _score(pipeline: str, requirement: str, descriptions: dict[str, str]) -> tuple[float, list[str]]:
    """Score one pipeline against the requirement. Returns (score, matched_signals)."""
    signals: list[str] = []
    score = 0.0
    norm = _normalize(requirement)
    for kw in KEYWORDS.get(pipeline, []):
        if kw in norm:
            score += 1.0
            signals.append(kw)
    desc = descriptions.get(pipeline, "")
    if desc:
        for kw in KEYWORDS.get(pipeline, []):
            if kw in desc and score == 0:
                # A description-level hint only weakly boosts; never beats a
                # direct keyword hit in the requirement.
                score += 0.25
    return score, signals


def select_pipeline(requirement: str) -> schema.PipelineSelection:
    """Map a natural-language requirement to one of the 13 pipelines.

    Deterministic: same input → same output. No LLM, no network, no paid
    service. ``confidence`` is a transparent match ratio, capped below 1.0 to
    signal that this is a heuristic, not a validated classifier.
    """
    norm = _normalize(requirement)
    descriptions = _load_descriptions()
    scored: list[tuple[str, float, list[str]]] = []
    for pipeline in KNOWN_PIPELINES:
        score, signals = _score(pipeline, norm, descriptions)
        scored.append((pipeline, score, signals))

    scored.sort(key=lambda x: (-x[1], KNOWN_PIPELINES.index(x[0]) if x[0] in KNOWN_PIPELINES else 999))

    best_pipeline, best_score, best_signals = scored[0]
    total = sum(s for _, s, _ in scored if s > 0) or 1.0
    # Transparent, capped confidence: a single weak signal can't look certain.
    confidence = min(0.9, (best_score / total) * min(1.0, best_score / 2.0)) if total else 0.0
    if best_score == 0:
        # No signal: fall back to the most general pipeline.
        best_pipeline = "animated-explainer"
        confidence = 0.15
        reason = "无明确信号，默认最通用的 animated-explainer。"
    else:
        reason = "匹配信号: " + ", ".join(best_signals)

    alternatives = [p for p, s, _ in scored[1:] if s > 0][:3]
    return schema.PipelineSelection(
        pipeline_type=best_pipeline,
        confidence=round(confidence, 2),
        reason=reason,
        alternatives=alternatives,
    )
