"""PM — the production manager (writable) for OpenMontage.

PM sits *alongside* the read-only Backlot board. It owns the writable layer:
project creation, status, cost budget, approvals, and a render-artifact index.
It never rewrites Backlot's read-only derived source files (checkpoints,
artifacts, scene_plan, asset_manifest, events.jsonl, …) — those stay owned by
the pipeline. PM reuses Backlot's read-only derivation (``backlot.state``) for
its detail/status/cost views so the two never drift.

Design contract (see the LSIT-285 contract, §1–§4):
- Coexist, don't rewrite: Backlot stays the read-only live board; PM is the
  new write layer sharing the same ``projects/<id>/`` data source.
- Zero paid / local / no paid AI: the default surface only exposes local or
  offline capabilities. Paid providers are shown as "未接入 / 需授权" and are
  never called by default.
- Never impersonate a real AI service: the conversational driver is a local
  rule-based orchestrator; any concept it produces is labelled an offline
  substitute and is NOT a validated real-AI generation.
- SQLite (stdlib ``sqlite3``) persists PM metadata; no third-party DB dep.

The agent's only duty is to run the server / CLI; the app degrades gracefully
like Backlot ("never block, never break").
"""

__version__ = "0.1.0"

# PM listens on its own port so it can run *next to* Backlot (4750) without a
# port clash. Override with the PM_PORT env var.
DEFAULT_PORT = 4751
