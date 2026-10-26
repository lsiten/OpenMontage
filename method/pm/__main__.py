"""PM CLI — the conversational + writable driver.

    python -m pm serve [--port N]        # run the PM server in the foreground
    python -m pm open [project-id]       # start server if needed, open the board
    python -m pm create --requirement "..." [--pipeline-type X]
    python -m pm chat "..." [--pipeline-type X] [--create]

PM is the writable layer next to the read-only Backlot board. It reuses the
13-pipeline selection logic and the registry provider menu, classifies local
vs paid cost, and — crucially — never calls a paid provider and never
impersonates a real AI service. The concept it produces is a labelled offline
substitute, not a validated real-AI generation.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser

from pm import DEFAULT_PORT
from pm import chat as chat_mod
from pm.store import get_db


def _port() -> int:
    try:
        return int(os.environ.get("PM_PORT", DEFAULT_PORT))
    except ValueError:
        return DEFAULT_PORT


def _server_alive(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def _spawn_server(port: int) -> None:
    """Start the server as a detached background process (never fatal)."""
    cmd = [sys.executable, "-m", "pm", "serve", "--port", str(port)]
    kwargs: dict = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        )
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)


def cmd_open(project_id: str | None) -> int:
    port = _port()
    if not _server_alive(port):
        try:
            _spawn_server(port)
        except Exception as exc:
            print(f"pm: could not start server ({exc}) — continuing without the board")
            return 1
        deadline = time.time() + 15
        while time.time() < deadline:
            if _server_alive(port):
                break
            time.sleep(0.4)
        else:
            print("pm: server did not come up in time — continuing without the board")
            return 1
    url = f"http://127.0.0.1:{port}/"
    if project_id:
        url = f"http://127.0.0.1:{port}/?project={project_id}"
    try:
        webbrowser.open(url)
    except Exception:
        pass
    print(f"pm: {url}")
    return 0


def cmd_serve(port: int) -> int:
    import uvicorn

    uvicorn.run("pm.server:app", host="127.0.0.1", port=port, log_level="warning")
    return 0


def _print_project(project) -> None:
    print(f"project_id: {project.project_id}")
    print(f"title:      {project.title}")
    print(f"pipeline:   {project.pipeline_type}")
    print(f"status:     {project.status} (source: {project.source})")
    if project.cost_estimate is not None:
        ce = project.cost_estimate
        print(
            f"cost:       local_usd={ce.total_local_usd}  "
            f"paid_usd={ce.total_paid_usd}  "
            f"(paid=分类，未接入/未调用; local={len(ce.local_capabilities)}, paid={len(ce.paid_capabilities)})"
        )


def cmd_create(requirement: str, pipeline_type: str = "") -> int:
    session = chat_mod.ChatSession(get_db())
    try:
        project = session.create_project(requirement, pipeline_override=pipeline_type)
    except Exception as exc:
        print(f"pm: could not create project ({exc})")
        return 1
    _print_project(project)
    print()
    print(f"pm: created {project.project_id} (status={project.status}, pipeline={project.pipeline_type})")
    print("pm: 这是离线替身/离线概念 — 不代表真实 AI 服务已接入，生成质量未验收。")
    return 0


def cmd_chat(requirement: str, pipeline_type: str = "", create: bool = False) -> int:
    session = chat_mod.ChatSession(get_db())
    proposal = session.propose(requirement, pipeline_override=pipeline_type)
    data = proposal.model_dump()
    if create:
        try:
            project = session.create_project(requirement, pipeline_override=pipeline_type)
            data["created_project_id"] = project.project_id
            data["created_status"] = project.status
        except Exception as exc:
            data["create_error"] = str(exc)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    if not create:
        print("\npm: 这是提案/离线替身；用 `pm create` 或 --create 创建项目（proposed 态）。")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pm", description=__doc__)
    sub = parser.add_subparsers(dest="command")

    p_serve = sub.add_parser("serve", help="run the PM server in the foreground")
    p_serve.add_argument("--port", type=int, default=_port())

    p_open = sub.add_parser("open", help="open the PM board in the browser (starts server if needed)")
    p_open.add_argument("project_id", nargs="?", default=None)

    p_create = sub.add_parser("create", help="create a PM project from a natural-language requirement")
    p_create.add_argument("--requirement", required=True)
    p_create.add_argument("--pipeline-type", default="", help="override auto pipeline selection")

    p_chat = sub.add_parser("chat", help="propose a project from a requirement (optionally create it)")
    p_chat.add_argument("requirement")
    p_chat.add_argument("--pipeline-type", default="", help="override auto pipeline selection")
    p_chat.add_argument("--create", action="store_true", help="also create the project (proposed state)")

    args = parser.parse_args(argv)
    if args.command == "serve":
        return cmd_serve(args.port)
    if args.command == "open":
        return cmd_open(args.project_id)
    if args.command == "create":
        return cmd_create(args.requirement, args.pipeline_type)
    if args.command == "chat":
        return cmd_chat(args.requirement, args.pipeline_type, args.create)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
