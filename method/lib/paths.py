"""Canonical repository paths — single source of truth.

The projects root is the most load-bearing path in the system: checkpoints
are written under it, tool events are attributed against it, and the Backlot
board watches it. Define it once.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Overridable for staging/screenshots/tests. Everything — checkpoint writes,
# event attribution, the Backlot board — follows the same root.
PROJECTS_DIR = Path(os.environ.get("OPENMONTAGE_PROJECTS_DIR") or (REPO_ROOT / "projects"))


def remotion_composer_dir(method_root: Path | None = None) -> Path:
    """Locate the shared composer in a monorepo or a standalone method checkout."""
    root = method_root if method_root is not None else REPO_ROOT
    if root.name == "method":
        shared = root.parent / "remotion-composer"
        if (shared / "package.json").is_file():
            return shared
    return root / "remotion-composer"
