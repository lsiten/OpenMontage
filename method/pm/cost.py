"""Local-vs-paid capability classification (the zero-paid boundary).

PM never calls a paid provider. Instead it *classifies* every capability from
the registry's provider menu into "local / offline" vs "paid / needs auth"
and shows the paid ones as "未接入/需授权". This is the AGENT_GUIDE provider-menu
contract ("你有的能力 + 你能解锁的能力") made explicit for PM.

Classification signal (in priority order):
  1. ToolRuntime — ``api`` => paid; ``local``/``local_gpu`` => local.
  2. Known paid provider names (the contract's list) — a secondary guard.
  3. ToolStatus — an ``api`` tool that is unavailable is shown as
     "未接入/需授权" (needs a paid key, not tried, not run).

Nothing here reserves budget, sets an env var, or calls a provider. A paid
capability is only ever *named*, never executed.
"""

from __future__ import annotations

from typing import Optional

from pm import schema

# --- The contract's paid-provider list (secondary guard) -----------------
# These require an API key + paid credits. PM names them as gaps, never runs
# them. Unknown paid/unknown-billing services are recorded as gaps, not tried.
PAID_PROVIDER_TOKENS = {
    # video generation
    "gemini", "veo", "sora", "seedance", "kling", "runway", "fal",
    "hunyuan", "hunyuancloud", "minimax", "grok", "jimeng", "higgsfield",
    "heygen", "seedream", "recraft", "atlas", "blender",
    # image
    "flux", "imagen", "google_imagen", "openai_image", "bfl",
    # audio / music / tts
    "elevenlabs", "suno", "azure", "google_tts", "google_music", "openai_tts",
    "dashscope", "doubao", "fish", "pixabay", "pexels", "freesound",
}

# Local / offline, zero-key (contract §4). These are the safe defaults.
LOCAL_PROVIDER_TOKENS = {
    "piper", "remotion", "hyperframes", "whisper", "ffmpeg", "openmontage",
    "local_diffusion", "comfyui", "manim", "d3", "local", "builtin",
    "offline",
}

STATUS_LABEL_UNCONFIGURED = "未接入/需授权"
STATUS_LABEL_LOCAL = "本地/离线"
STATUS_LABEL_LOCAL_GPU = "本地/需GPU"

def _as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        return " / ".join(str(v) for v in value if v)
    return str(value)



def _has_paid_token(*strings: str) -> bool:
    for s in strings:
        if not s:
            continue
        low = s.lower()
        if any(tok in low for tok in PAID_PROVIDER_TOKENS):
            return True
    return False


def _has_local_token(*strings: str) -> bool:
    for s in strings:
        if not s:
            continue
        low = s.lower()
        if any(tok in low for tok in LOCAL_PROVIDER_TOKENS):
            return True
    return False


def classify_entry(entry: dict, capability: str = "") -> schema.CapabilityEntry:
    """Classify one provider-menu entry into a local|paid capability cell."""
    name = entry.get("name", "")
    provider = entry.get("provider", "")
    cap = capability or entry.get("capability", "")
    runtime = entry.get("runtime", "unknown")
    status = entry.get("status", "unavailable")

    is_paid = False
    is_local = False

    if runtime == "api":
        is_paid = True
    elif runtime in ("local", "local_gpu"):
        is_local = True
    elif runtime == "hybrid":
        # A hybrid tool can run locally OR via API; if a local path is
        # available we count it as local, else it needs a paid key.
        is_local = status == "available" or _has_local_token(provider, name)
        is_paid = not is_local

    # Secondary guard: a named paid provider is paid regardless of runtime.
    if _has_paid_token(provider, name):
        is_paid = True
        is_local = False

    # Local GPU tools are local but need a GPU — still free, still offline.
    if runtime == "local_gpu":
        is_local = True
        is_paid = False

    if is_local:
        status_label = STATUS_LABEL_LOCAL_GPU if runtime == "local_gpu" else STATUS_LABEL_LOCAL
    else:
        # A paid capability that is not configured is "未接入/需授权" — PM
        # never tries it. This is the hard "no paid AI" boundary.
        status_label = STATUS_LABEL_UNCONFIGURED

    return schema.CapabilityEntry(
        capability=cap,
        provider=provider,
        tool=name or None,
        runtime=runtime,
        status=status,
        is_local=is_local,
        is_paid=is_paid,
        best_for=_as_text(entry.get("best_for", "")),
        status_label=status_label,
        install_instructions=_as_text(entry.get("install_instructions", "")),
    )


def build_capability_report(registry: Optional[object] = None) -> dict:
    """Classify the whole provider menu into local vs paid capability cells.

    Returns a dict shaped for the agent's preflight provider menu:
    ``{"local": [...], "paid": [...], "by_capability": {...}, "summary": {...}}``.
    """
    if registry is None:
        from tools.tool_registry import registry as _registry
        registry = _registry
    try:
        menu = registry.provider_menu()
    except Exception:
        # Registry unavailable → degrade to an empty (but valid) report.
        return {"local": [], "paid": [], "by_capability": {},
                "summary": {"local": 0, "paid": 0, "unconfigured_paid": 0}}

    local: list[schema.CapabilityEntry] = []
    paid: list[schema.CapabilityEntry] = []
    by_cap: dict[str, list[schema.CapabilityEntry]] = {}
    for cap, bucket in menu.items():
        for entry in bucket.get("available", []) + bucket.get("unavailable", []):
            classified = classify_entry(entry, cap)
            by_cap.setdefault(cap, []).append(classified)
            if classified.is_local and not classified.is_paid:
                local.append(classified)
            else:
                paid.append(classified)

    unconfigured_paid = sum(1 for c in paid if c.status != "available")
    summary = {
        "local": len(local),
        "paid": len(paid),
        "unconfigured_paid": unconfigured_paid,
        "capabilities": sorted(by_cap.keys()),
    }
    return {"local": local, "paid": paid, "by_capability": by_cap, "summary": summary}


def estimate_cost(
    pipeline_type: str,
    concept: str = "",
    requirement: str = "",
    registry: Optional[object] = None,
) -> schema.CostEstimate:
    """Produce a local/paid cost classification for a selected pipeline.

    This is a *classification*, not a reservation. ``total_paid_usd`` stays
    0.0 because PM never calls a paid provider; the paid entries are named so
    the agent can present them as "未接入/需授权" and route any real call
    through proposal approval + cost_tracker.reserve + user confirmation.
    """
    report = build_capability_report(registry)
    estimate = schema.CostEstimate(
        total_local_usd=0.0,
        total_paid_usd=0.0,
        local_capabilities=report["local"],
        paid_capabilities=report["paid"],
        notes=[
            "视频制作统一使用 OpenReel；工具分类不表示制作路由或实际接入，Remotion 不是必需依赖。",
            "付费 provider 仅分类、不接入、不调用；显示为“未接入/需授权”。",
            "任何付费调用仍需 proposal 审批 + cost_tracker.reserve + 用户确认。",
        ],
    )
    # A rough, safe local estimate: local-only capabilities have no paid
    # component, so the local budget is 0 unless a local GPU tool is involved
    # (still free, no paid call). We never fabricate a paid dollar figure.
    return estimate
