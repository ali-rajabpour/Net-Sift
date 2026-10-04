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
    "BRAVE_API_KEY": "enables the Brave Search API web source (metered)",
    "MARGINALIA_API_KEY": "personal Marginalia key; adds it to the default sweep",
}


def ensure_dirs() -> None:
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


#: Which browser net-sift manages (its profile is copied and driven headless).
_BROWSER_CHOICE = HOME / "browser.json"


def get_browser_choice(home: Path) -> str | None:
    try:
        return json.loads((Path(home) / "browser.json").read_text(encoding="utf-8")).get("browser")
    except (OSError, ValueError):
        return None


def set_browser_choice(home: Path, browser_id: str) -> None:
    Path(home).mkdir(parents=True, exist_ok=True)
    (Path(home) / "browser.json").write_text(json.dumps({"browser": browser_id}), encoding="utf-8")


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
    """Persist a provider key to ~/.net-sift/secrets.json. The file is created with
    0600 from the start (os.open), so the key is never briefly world-readable."""
    HOME.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(_SECRETS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    data[name] = value
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(_SECRETS, flags, stat.S_IRUSR | stat.S_IWUSR)  # 0600 at creation
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    # Correct perms even if the file pre-existed with looser bits (O_CREAT mode
    # only applies on creation).
    try:
        os.chmod(_SECRETS, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass
