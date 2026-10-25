"""PM server — FastAPI app: writable CRUD + read views reusing Backlot.

PM is the writable layer next to the read-only Backlot board. It shares the
same ``projects/<id>/`` data source and the same Backlot derivation
(``load_board_state`` / ``list_projects``) for read views, and adds a
writable SQLite metadata layer. It only ever writes PM metadata (SQLite +
the ``pm`` segment of project.json); it never rewrites Backlot's read-only
derived source files.

Zero paid / no real AI: the chat endpoints never call a paid provider and
never impersonate a real AI service; paid capabilities are classified and
named as "未接入/需授权".
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from pm import DEFAULT_PORT
from pm import chat as chat_mod
from pm import cost as cost_mod
from pm import schema
from pm import state as state_mod
from pm.store import get_db

UI_DIR = Path(__file__).resolve().parent / "ui"


def _db():
    return get_db()


def create_app() -> FastAPI:
    app = FastAPI(title="PM (production manager)", docs_url=None, redoc_url=None)

    # ---- health -------------------------------------------------------

    @app.get("/api/health")
    async def health() -> dict:
        return {"ok": True, "app": "pm", "port": DEFAULT_PORT}

    # ---- CRUD --------------------------------------------------------

    @app.post("/api/projects", status_code=201)
    async def create_project(req: schema.ProjectCreate) -> dict:
        # Create through the PM write layer (init_project + store + pm segment).
        session = chat_mod.ChatSession(_db())
        project = await asyncio.to_thread(
            session.create_project, req.requirement, req.pipeline_type
        )
        # Apply the explicit budget / mode / source from the request.
        update = schema.ProjectUpdate(
            title=req.title or project.title,
            cost_budget_usd=req.cost_budget_usd,
            mode=req.mode,
            source=req.source,
            status="proposed",
        )
        project = await asyncio.to_thread(_db().update_project, project.project_id, update)
        return _project_json(project)

    @app.get("/api/projects")
    async def list_projects() -> list:
        return await asyncio.to_thread(state_mod.list_project_views, _db())

    @app.get("/api/projects/{project_id}")
    async def get_project(project_id: str) -> dict:
        view = await asyncio.to_thread(state_mod.load_project_view, project_id, _db())
        if view.get("pm") is None:
            raise HTTPException(status_code=404, detail=f"unknown project: {project_id}")
        return view

    @app.put("/api/projects/{project_id}")
    async def update_project(project_id: str, req: schema.ProjectUpdate) -> dict:
        updated = await asyncio.to_thread(_db().update_project, project_id, req)
        if updated is None:
            raise HTTPException(status_code=404, detail=f"unknown project: {project_id}")
        return _project_json(updated)

    @app.delete("/api/projects/{project_id}", status_code=204)
    async def delete_project(project_id: str) -> None:
        ok = await asyncio.to_thread(_db().delete_project, project_id)
        if not ok:
            raise HTTPException(status_code=404, detail=f"unknown project: {project_id}")

    # ---- views -------------------------------------------------------

    @app.get("/api/projects/{project_id}/status")
    async def status_view(project_id: str) -> dict:
        return await asyncio.to_thread(state_mod.status_view, project_id, _db())

    @app.get("/api/projects/{project_id}/cost")
    async def cost_view(project_id: str) -> dict:
        return await asyncio.to_thread(state_mod.cost_view, project_id, _db())

    @app.get("/api/capabilities")
    async def capabilities() -> dict:
        return await asyncio.to_thread(cost_mod.build_capability_report)

    # ---- chat (conversational driver) --------------------------------

    @app.post("/api/chat/propose")
    async def propose(req: schema.ProjectCreate) -> dict:
        # Requirement -> proposal packet. No execution, no paid call.
        proposal = await asyncio.to_thread(
            chat_mod.build_proposal, req.requirement, None, req.pipeline_type
        )
        return proposal.model_dump()

    @app.post("/api/chat")
    async def chat_create(req: schema.ProjectCreate) -> dict:
        session = chat_mod.ChatSession(_db())
        proposal = await asyncio.to_thread(session.build, req.requirement, req.pipeline_type)
        return proposal.model_dump()

    # ---- UI ----------------------------------------------------------

    @app.get("/")
    async def index() -> HTMLResponse:
        html = (UI_DIR / "index.html").read_text(encoding="utf-8")
        for asset in ("index.css", "index.js"):
            path = UI_DIR / asset
            if path.is_file():
                version = str(int(path.stat().st_mtime))
                html = html.replace(f"/ui/{asset}", f"/ui/{asset}?v={version}")
        return HTMLResponse(html)

    if UI_DIR.is_dir():
        app.mount("/ui", StaticFiles(directory=UI_DIR), name="ui")

    @app.middleware("http")
    async def ui_no_cache(request, call_next):
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/ui"):
            response.headers["Cache-Control"] = "no-cache"
        return response

    return app


def _project_json(project: schema.PmProject) -> dict:
    data = project.model_dump()
    if project.cost_estimate is not None:
        data["cost_estimate"] = project.cost_estimate.model_dump()
    return data


app = create_app()
