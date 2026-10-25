"""PM — the production management application for OpenMontage.

A local, zero-paid write layer that sits ALONGSIDE the read-only Backlot board.
Backlot keeps deriving live board state from the pipeline's own files (it never
writes). PM owns the *writable* project metadata — create / status / cost budget
/ approvals / artifact index — persisted in SQLite and associated with the
runtime ``projects/<id>/`` directory by ``project_id``.

Design contract (see LSIT-285 design/contract doc, accepted by the producer):
- Two capabilities: (1) an independent PM application with CRUD + list / detail /
  status / cost views; (2) a local dialog-driven entry that turns a natural
  language brief into a pipeline selection + concept + cost proposal and (when
  triggered) creates the project record. It reuses the 13 existing agentic
  pipelines' "pipeline selection" logic and does NOT add a new execution engine.
- Zero paid / local / no paid AI. The entry never calls a paid provider; any
  paid call still requires proposal approval + ``cost_tracker.reserve`` + user
  confirmation (out of scope for this run — we do not trial-run paid services).
- Offline / mock material is labeled "未接入/未验收" (not connected / not
  verified) and must never be presented as a real AI service.
- Backlot's read-only contract (``tests/contracts/test_backlot_contract.py``)
  is untouched; PM only reads via ``backlot.state`` and writes its own layer.
"""

__version__ = "0.1.0"
