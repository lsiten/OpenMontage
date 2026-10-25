"""PM server — FastAPI app: CRUD + dialog entry + capabilities (zero paid).

Runs alongside the Backlot board. It exposes the PM write model (CRUD), the
dialog entry (brief -> plan / trigger), and the local/paid capability menu. It
reads Backlot-derived board state for the detail view via ``backlot.state``
(read-only) and writes only the PM layer. It never writes Backlot's read-only
derive files and never calls a paid provider.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from pm import store
from pm.capabilities import list_capabilities
from pm.chat import plan, trigger
from pm.schemas import (
    ApprovalDecision,
    ApprovalRequest,
    ChatRequest,
    ProjectCreate,
    ProjectUpdate,
    TriggerRequest,
)

UI_DIR = Path(__file__).resolve().parent / "ui"


def _ui_html(name: str) -> HTMLResponse:
    path = UI_DIR / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"ui not found: {name}")
    html = path.read_text(encoding="utf-8")
    return HTMLResponse(html)


def create_app() -> FastAPI:
    app = FastAPI(title="PM (Production Management)", docs_url=None, redoc_url=None)

    # ---- Health --------------------------------------------------------

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True, "app": "pm"}

    # ---- CRUD --------------------------------------------------------

    @app.get("/api/projects")
    async def projects() -> list:
        return [p.model_dump() for p in await asyncio.to_thread(store.list_projects)]

    @app.get("/api/project/{project_id}")
    async def project(project_id: str) -> dict:
        p = await asyncio.to_thread(store.get_project, project_id)
        if p is None:
            raise HTTPException(status_code=404, detail=f"unknown project: {project_id}")
        return p.model_dump()

    @app.post("/api/project")
    async def create_project(payload: ProjectCreate) -> dict:
        p = await asyncio.to_thread(store.create_project, payload)
        return p.model_dump()

    @app.patch("/api/project/{project_id}")
    async def update_project(project_id: str, payload: ProjectUpdate) -> dict:
        p = await asyncio.to_thread(store.update_project, project_id, payload)
        if p is None:
            raise HTTPException(status_code=404, detail=f"unknown project: {project_id}")
        return p.model_dump()

    @app.post("/api/project/{project_id}/status")
    async def set_status(project_id: str, payload: ProjectUpdate) -> dict:
        if payload.status is None:
            raise HTTPException(status_code=400, detail="status required")
        p = await asyncio.to_thread(store.set_status, project_id, payload.status, payload.updated_by)
        if p is None:
            raise HTTPException(status_code=404, detail=f"unknown project: {project_id}")
        return p.model_dump()

    # ---- Approvals ---------------------------------------------------

    @app.post("/api/project/{project_id}/approval")
    async def request_approval(project_id: str, payload: ApprovalRequest) -> dict:
        if store.get_project(project_id) is None:
            raise HTTPException(status_code=404, detail=f"unknown project: {project_id}")
        a = await asyncio.to_thread(store.request_approval, project_id, payload)
        return a.model_dump()

    @app.get("/api/project/{project_id}/approvals")
    async def approvals(project_id: str) -> list:
        return [a.model_dump() for a in await asyncio.to_thread(store.list_approvals, project_id)]

    @app.post("/api/project/{project_id}/approval/{approval_id}/decision")
    async def decide(
        project_id: str, approval_id: int, payload: ApprovalDecision
    ) -> dict:
        a = await asyncio.to_thread(store.decide_approval, approval_id, payload.status, payload.decided_by)
        if a is None or a.project_id != project_id:
            raise HTTPException(status_code=404, detail="approval not found")
        # Approving the budget/approval flips the project's approved flag.
        if payload.status == "approved":
            store.update_project(project_id, ProjectUpdate(approved=True, updated_by=payload.decided_by))
        return a.model_dump()

    # ---- Cost / detail (read via backlot derive) --------------------

    @app.get("/api/project/{project_id}/cost")
    async def cost(project_id: str) -> dict:
        p = await asyncio.to_thread(store.get_project, project_id)
        if p is None:
            raise HTTPException(status_code=404, detail=f"unknown project: {project_id}")
        return {
            "project_id": project_id,
            "cost_budget_usd": p.cost_budget_usd,
            "cost_reserved_usd": p.cost_reserved_usd,
            "cost_spent_usd": p.cost_spent_usd,
            "cost_mode": p.cost_mode,
            "currency": "usd",
        }

    @app.get("/api/project/{project_id}/state")
    async def project_state(project_id: str) -> dict:
        """Read-only board state derived from the runtime project dir.

        Reuses Backlot's read-only derive; PM writes nothing here.
        """
        from backlot.state import load_board_state
        from lib.paths import PROJECTS_DIR

        pdir = PROJECTS_DIR / project_id
        if not pdir.is_dir():
            return {"project_id": project_id, "has_pipeline_state": False}
        return await asyncio.to_thread(load_board_state, pdir)

    @app.get("/api/project/{project_id}/detail")
    async def detail(project_id: str) -> dict:
        p = await asyncio.to_thread(store.get_project, project_id)
        if p is None:
            raise HTTPException(status_code=404, detail=f"unknown project: {project_id}")
        board = await asyncio.to_thread(
            _safe_board_state, project_id
        )
        return {
            "pm": p.model_dump(),
            "board": board,
            "approvals": [a.model_dump() for a in await asyncio.to_thread(store.list_approvals, project_id)],
            "artifacts": await asyncio.to_thread(store.list_artifacts, project_id),
        }

    # ---- Dialog entry -----------------------------------------------

    @app.post("/api/chat")
    async def chat(req: ChatRequest) -> dict:
        resp = await asyncio.to_thread(plan, req)
        return resp.model_dump()

    @app.post("/api/chat/trigger")
    async def chat_trigger(req: TriggerRequest) -> dict:
        resp = await asyncio.to_thread(trigger, req)
        return resp.model_dump()

    # ---- Capabilities / cost boundary -------------------------------

    @app.get("/api/capabilities")
    async def capabilities() -> dict:
        caps = await asyncio.to_thread(list_capabilities)
        local = [c.model_dump() for c in caps if c.classification == "local"]
        paid = [c.model_dump() for c in caps if c.classification == "paid"]
        return {
            "local": local,
            "paid": paid,
            "total": len(caps),
            "local_available": sum(1 for c in local if c.get("status") == "available"),
            "note": "本地/离线能力优先；付费能力显示未接入/需授权，不默认调用。",
        }

    # ---- UI --------------------------------------------------------

    @app.get("/")
    async def index() -> HTMLResponse:
        return _ui_html("index.html")

    @app.get("/chat")
    async def chat_page() -> HTMLResponse:
        return _ui_html("chat.html")

    @app.get("/p/{project_id}")
    async def detail_page(project_id: str) -> HTMLResponse:
        return _ui_html("detail.html")

    if UI_DIR.is_dir():
        app.mount("/ui", StaticFiles(directory=UI_DIR), name="ui")

    @app.middleware("http")
    async def ui_no_cache(request, call_next):
        response = await call_next(request)
        path = request.url.path
        if path in ("/", "/chat") or path.startswith("/ui") or path.startswith("/p/"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    return app


def _safe_board_state(project_id: str) -> dict:
    """Read-only board state; never raises (Backlot's never-block contract)."""
    from backlot.state import load_board_state
    from lib.paths import PROJECTS_DIR

    pdir = PROJECTS_DIR / project_id
    if not pdir.is_dir():
        return {"project_id": project_id, "has_pipeline_state": False}
    try:
        return load_board_state(pdir)
    except Exception:
        return {"project_id": project_id, "has_pipeline_state": False, "error": "unreadable"}


app = create_app()
