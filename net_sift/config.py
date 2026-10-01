"""Runtime configuration. Everything is resolved from the environment so the tool
stays portable; no OS keychain, no secrets on disk in this repo."""

from __future__ import annotations

import os
from pathlib import Path

#: Root for session storage and caches. Override with NET_SIFT_HOME.
HOME = Path(os.environ.get("NET_SIFT_HOME", "~/.net-sift")).expanduser()
SESSIONS_DIR = HOME / "sessions"

#: Engine defaults.
DEFAULT_BUDGET = 2000  # per-source, per-window record cap
DEFAULT_NEAR_DUP = 0.85  # same-source near-duplicate collapse threshold
DEFAULT_MIN_REL = 0.1  # relevance floor for ranking

#: Optional environment keys the tool will use if present (never required).
OPTIONAL_ENV = {
    "GITHUB_TOKEN": "lifts the GitHub Search API rate limit",
}


def ensure_dirs() -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
