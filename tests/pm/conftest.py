"""Shared fixtures for PM tests — isolated temp SQLite + temp projects dir.

The PM store keeps a single lock-guarded connection as a module global. These
fixtures point it at a unique temp SQLite per test and a shared temp projects
dir (so marker writes never touch the real ``projects/`` or the source tree),
then reset the store between tests.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def pm_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db = tmp_path / "pm.sqlite"
    projects = tmp_path / "projects"
    monkeypatch.setenv("OPENMONTAGE_PM_DB", str(db))
    monkeypatch.setenv("OPENMONTAGE_PROJECTS_DIR", str(projects))
    from pm import store

    store.reset()
    yield
    store.reset()
