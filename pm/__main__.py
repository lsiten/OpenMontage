"""PM CLI.

    python -m pm serve [--port N]   # run the PM server in the foreground
    python -m pm open [--port N]    # start server if needed, open browser

``open`` mirrors Backlot: idempotent and non-fatal.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser

DEFAULT_PORT = 4751


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
    cmd = [sys.executable, "-m", "pm", "serve", "--port", str(port)]
    kwargs: dict = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL, "stdin": subprocess.DEVNULL}
    if os.name == "nt":
        kwargs["creationflags"] = (
            subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        )
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(cmd, **kwargs)


def cmd_serve(port: int) -> int:
    import uvicorn

    uvicorn.run("pm.server:app", host="127.0.0.1", port=port, log_level="warning")
    return 0


def cmd_open(port: int) -> int:
    if not _server_alive(port):
        try:
            _spawn_server(port)
        except Exception as exc:
            print(f"pm: could not start server ({exc}) — continuing without the app")
            return 1
        deadline = time.time() + 15
        while time.time() < deadline:
            if _server_alive(port):
                break
            time.sleep(0.4)
        else:
            print("pm: server did not come up in time — continuing without the app")
            return 1
    url = f"http://127.0.0.1:{port}/"
    try:
        webbrowser.open(url)
    except Exception:
        pass
    print(f"pm: {url}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="pm", description=__doc__)
    sub = parser.add_subparsers(dest="command")
    p_serve = sub.add_parser("serve", help="run the PM server in the foreground")
    p_serve.add_argument("--port", type=int, default=_port())
    p_open = sub.add_parser("open", help="open the PM app in the browser (starts server if needed)")
    p_open.add_argument("--port", type=int, default=_port())
    args = parser.parse_args(argv)
    if args.command == "serve":
        return cmd_serve(args.port)
    if args.command == "open":
        return cmd_open(args.port)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
