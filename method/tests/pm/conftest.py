"""Fixtures for the pm/ test suite.

Isolation strategy (never touch the real repo `projects/` or a real `.pm/` DB):
  * A throwaway env is set at import time so the module-level singletons
    (PROJECTS_DIR, PM_DB_PATH) resolve to a temp location before any test
    module imports pm.
  * Per-test fixtures then monkeypatch the PROJECTS_DIR names on every module
    that reads them, and hand out a fresh SQLite DB, so tests cannot share
    state with each other or with the real workspace.
"""

from __future__ import annotations

import os
import pathlib
import tempfile

import pytest

# Resolve the module-level singletons to a throwaway location at import time
# (runs before any test module imports pm / backlot).
_TMP_OWNER = tempfile.TemporaryDirectory(prefix="pm_test_")
_TMP = pathlib.Path(_TMP_OWNER.name)
os.environ["OPENMONTAGE_PROJECTS_DIR"] = str(_TMP / "projects")
os.environ["PM_DB_PATH"] = str(_TMP / "pm.db")


@pytest.fixture
def db(tmp_path):
    """A fresh, explicit SQLite store (bypasses the module singleton)."""
    from pm.store import PMDatabase

    d = PMDatabase(tmp_path / "pm.db")
    yield d
    d.close()


@pytest.fixture
def projects_dir(monkeypatch, tmp_path):
    """Point every PROJECTS_DIR reference at a per-test temp dir."""
    d = tmp_path / "projects"
    d.mkdir(exist_ok=True)
    import backlot.state
    import lib.checkpoint
    import lib.paths
    import pm.state

    for mod in (lib.paths, backlot.state, pm.state, lib.checkpoint):
        if hasattr(mod, "PROJECTS_DIR"):
            monkeypatch.setattr(mod, "PROJECTS_DIR", d)
    yield d


@pytest.fixture
def client(tmp_path, monkeypatch, projects_dir):
    """A TestClient against the pm app with an isolated DB + projects dir."""
    import pm.store

    monkeypatch.setattr(pm.store, "_DB_PATH", tmp_path / "pm.db")
    pm.store._db = None  # force get_db() to (re)build against the new path
    from starlette.testclient import TestClient

    from pm.server import app

    yield TestClient(app)
