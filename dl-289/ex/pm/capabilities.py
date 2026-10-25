"""Capability + cost classification — reuse the tool registry, never call a
paid provider.

The dialog entry must expose "what you have + what you can unlock" (the
AGENT_GUIDE Provider Menu contract) and classify cost local-vs-paid. This module
reuses ``tools.tool_registry`` (provider_menu) to REPORT availability. Reporting
never invokes a provider and never costs money; it only reads the registry (and
optionally a .env presence). The hard zero-paid boundary is enforced here:
nothing in this module makes a generation call, and paid rows are always
classified ``未接入/需授权``.
"""

from __future__ import annotations

from typing import Any

from pm.schemas import UNCONNECTED, CapabilityInfo

# ToolRuntime -> local/paid classification. LOCAL + LOCAL_GPU are free on-device
# (LOCAL_GPU is still free, just needs a GPU); API is paid; HYBRID has a free
# local path so we treat it as local-capable while noting the API option.
_LOCAL_RUNTIMES = {"local", "local_gpu"}
_PAID_RUNTIMES = {"api"}


def _classify(runtime: str) -> str:
    r = (runtime or "").lower()
    if r in _PAID_RUNTIMES:
        return "paid"
    if r in _LOCAL_RUNTIMES or r == "hybrid":
        return "local"
    # Unknown runtime: be conservative — treat as paid/unconnected.
    return "paid"


def provider_menu() -> dict[str, Any]:
    """The provider menu from the registry (report-only, no generation call)."""
    from tools.tool_registry import registry

    registry.discover()
    return registry.provider_menu()


def list_capabilities() -> list[CapabilityInfo]:
    """All capabilities, classified local vs paid, with an honest status note.

    The provider menu groups tools by capability (the dict key). Each entry is
    reported, never invoked. Paid+unavailable rows are labeled UNCONNECTED.
    """
    out: list[CapabilityInfo] = []
    for cap_name, bucket in provider_menu().items():
        for entry in list(bucket.get("available", [])) + list(bucket.get("unavailable", [])):
            runtime = entry.get("runtime", "api")
            classification = _classify(runtime)
            status = entry.get("status", "unavailable")
            note = ""
            if classification == "paid":
                if status != "available":
                    note = UNCONNECTED  # not connected / requires authorization
                else:
                    note = "付费能力已配置，但本入口不默认调用；需 proposal 审批 + reserve。"
            elif status != "available":
                note = "本地能力未就绪（缺失依赖/运行时）。"
            out.append(
                CapabilityInfo(
                    capability=cap_name,
                    tool=entry.get("name", ""),
                    provider=entry.get("provider", ""),
                    runtime=runtime,
                    classification=classification,
                    status=status,
                    note=note,
                )
            )
    out.sort(key=lambda c: (c.classification != "local", c.capability, c.tool))
    return out


def split_capabilities(
    capabilities: list[CapabilityInfo],
) -> tuple[list[CapabilityInfo], list[CapabilityInfo]]:
    """Return (local, paid) capability lists."""
    local = [c for c in capabilities if c.classification == "local"]
    paid = [c for c in capabilities if c.classification == "paid"]
    return local, paid
