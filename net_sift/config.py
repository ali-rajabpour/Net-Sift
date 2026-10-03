"""Runtime configuration. Everything is resolved from the environment so the tool
stays portable; no OS keychain, no secrets on disk in this repo."""

from __future__ import annotations

import json
import os
import stat
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


#: Optional provider keys for opt-in features. Read from the environment first,
#: then a local secrets file the wizard writes. Never committed; never required.
_SECRETS = HOME / "secrets.json"


def get_secret(name: str) -> str | None:
    v = os.environ.get(name)
    if v:
        return v
    try:
        return json.loads(_SECRETS.read_text(encoding="utf-8")).get(name)
    except (OSError, ValueError):
        return None


def set_secret(name: str, value: str) -> None:
    """Persist a provider key to ~/.net-sift/secrets.json with 0600 perms."""
    HOME.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(_SECRETS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data[name] = value
    _SECRETS.write_text(json.dumps(data, indent=2), encoding="utf-8")
    try:
        _SECRETS.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600
    except OSError:
        pass
