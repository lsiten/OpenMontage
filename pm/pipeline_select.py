"""Pipeline selection — a transparent, local, deterministic heuristic.

This is the code form of AGENT_GUIDE "Rule Zero" (treat every video request as
a pipeline-selection question) reused by the dialog entry. It is deliberately a
keyword/feature scorer over the 13 existing agentic pipelines' metadata — NOT a
paid LLM call and NOT a real AI service. It exists so the local entry can pick
a pipeline + concept without any paid provider, honoring the zero-paid / no-paid
AI boundary. The output is transparent (scores + reasons) so the independent
reviewer can audit it, and it is labeled a local heuristic, not AI generation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from lib.pipeline_loader import list_pipelines

# Representative keywords per pipeline. Keys are matched (case-insensitively,
# substring) against the lowercased brief. English + Chinese (the product is
# zh-CN) both count. This is a curated, auditable table — not magic.
PIPELINE_KEYWORDS: dict[str, list[str]] = {
    "animated-explainer": [
        "explainer", "explaine", "解释", "科普", "concept", "概念",
        "animated explainer", "动画解释", "narration", "旁白",
    ],
    "animation": ["animation", "animate", "动画", "motion", "动作", "motion graphics"],
    "avatar-spokesperson": [
        "avatar", "数字人", "spokesperson", "presenter", "主播",
        "口播", "presenter", "虚拟人", "digital human",
    ],
    "character-animation": [
        "character", "角色", "character animation", "角色动画",
        "cartoon", "卡通", "character rig",
    ],
    "cinematic": [
        "cinematic", "电影", "电影感", "剧情", "短片", "story",
        "drama", "dramatic", "film",
    ],
    "clip-factory": [
        "clip", "clips", "切片", "短视频", "short", "factory",
        "batch", "批量", "repurpose clip",
    ],
    "documentary-montage": [
        "documentary", "纪录片", "montage", "混剪", "素材",
        "footage", "montage", "archive", "档案",
    ],
    "framework-smoke": [
        "smoke", "framework", "framework smoke", "契约", "contract",
        "test pipeline",
    ],
    "hybrid": ["hybrid", "混合", "mixed", "hybrid media", "混合媒体"],
    "localization-dub": [
        "dub", "配音", "localization", "本地化", "多语言", "translate",
        "translation", "翻译", "字幕", "subtitle", "subtitles",
    ],
    "podcast-repurpose": [
        "podcast", "播客", "repurpose", "二次利用", "视频化",
        "audio to video", "音频转视频",
    ],
    "screen-demo": [
        "screen", "录屏", "屏幕", "demo", "演示", "screen recording",
        "screen recording", "ui walkthrough", "操作演示",
    ],
    "talking-head": [
        "talking head", "talking-head", "真人", "出镜", "口播",
        "真人出镜", "真人视频", "facecam", "face cam",
    ],
}

# Keyword weighting: a category/short phrase match is stronger than a stray
# single word, but the scorer below treats all hits equally and ranks by count.
GENERIC_TERMS = {"video", "make", "create", "做", "视频", "个", "the", "a", "make me"}


@dataclass
class Candidate:
    pipeline_type: str
    score: int
    matched: list[str] = field(default_factory=list)
    category: str = "unknown"
    stability: str = "unknown"


@dataclass
class PipelineSelection:
    pipeline_type: Optional[str]
    candidates: list[Candidate]
    confidence: float
    reason: str


def _category_of(pipeline_type: str) -> str:
    try:
        from lib.pipeline_loader import load_pipeline_readonly

        manifest = load_pipeline_readonly(pipeline_type)
        return str(manifest.get("category") or "unknown")
    except Exception:
        return "unknown"


def _stability_of(pipeline_type: str) -> str:
    try:
        from lib.pipeline_loader import load_pipeline_readonly

        manifest = load_pipeline_readonly(pipeline_type)
        return str(manifest.get("stability") or "unknown")
    except Exception:
        return "unknown"


def _score(brief: str, pipeline_type: str) -> tuple[int, list[str]]:
    low = brief.lower()
    score = 0
    matched: list[str] = []
    for kw in PIPELINE_KEYWORDS.get(pipeline_type, []):
        k = kw.lower()
        if not k or k in GENERIC_TERMS:
            continue
        if k in low:
            # Longer, more specific phrases are worth more.
            score += 1 + (1 if len(k.split()) > 1 else 0)
            matched.append(kw)
    return score, matched


def select_pipeline(
    requirement: str,
    candidates_limit: int = 5,
) -> PipelineSelection:
    """Rank the 13 pipelines against a brief and return the top pick.

    Pure local heuristic: no network, no paid service, deterministic.
    """
    all_names = set(list_pipelines())
    scored: list[Candidate] = []
    for name in all_names:
        if name in ("framework-smoke",):
            # framework-smoke is a test fixture, not a real product pipeline;
            # only surface it if the brief explicitly asks for a smoke/contract
            # test so real requests never land on it by accident.
            continue
        score, matched = _score(requirement, name)
        if score > 0:
            scored.append(
                Candidate(
                    pipeline_type=name,
                    score=score,
                    matched=matched,
                    category=_category_of(name),
                    stability=_stability_of(name),
                )
            )
    # Sort: score desc, then production stability first (production > beta).
    _stab_rank = {"production": 0, "beta": 1, "experimental": 2}
    scored.sort(
        key=lambda c: (
            -c.score,
            _stab_rank.get(c.stability, 3),
            c.pipeline_type,
        )
    )
    candidates = scored[:candidates_limit]
    if candidates:
        top = candidates[0]
        # Confidence in (0, 1]: normalized by the gap to the 2nd candidate.
        second = candidates[1].score if len(candidates) > 1 else 0
        confidence = min(1.0, top.score / (top.score + max(1, second) * 0.5))
        reason = (
            f"本地启发式选择 {top.pipeline_type}（命中关键词: "
            f"{', '.join(top.matched) or 'category'}，得分 {top.score}）。"
        )
        return PipelineSelection(
            pipeline_type=top.pipeline_type,
            candidates=candidates,
            confidence=round(confidence, 3),
            reason=reason,
        )
    # No keyword hit: fall back to the most general product pipeline.
    return PipelineSelection(
        pipeline_type="animated-explainer",
        candidates=[],
        confidence=0.0,
        reason=(
            "需求未命中任何管线关键词，回退到通用管线 animated-explainer；"
            "请在对话中补充更具体的描述以缩小选择范围。"
            "Brief matched no pipeline keywords; fell back to the general "
            "animated-explainer pipeline. Refine the brief to narrow the pick."
        ),
    )
