"""Search sessions: durable storage so a sweep can be continued later, deleted
only on explicit confirmation.

Each session is a directory under ``~/.net-sift/sessions/<id>/`` holding
``corpus.jsonl`` (the full ranked records) and ``meta.json`` (query, params,
counts, logs). The MCP layer returns only summaries and this path; the corpus is
kept until the user confirms a ``cleanup``. No scratch or temp files are left
behind: the corpus is the single durable artifact.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from . import config


def _slug(text: str, n: int = 24) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:n] or "search"


def new_id(query: str) -> str:
    return f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{_slug(query, 16)}"


def _dir(session_id: str) -> Path:
    return config.SESSIONS_DIR / session_id


def save(query: str, params: dict, records: list[dict], logs: list[str]) -> dict:
    """Write a finished search. Returns the session meta (no raw records)."""
    config.ensure_dirs()
    sid = new_id(query)
    d = _dir(sid)
    d.mkdir(parents=True, exist_ok=True)
    with (d / "corpus.jsonl").open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    breakdown: dict[str, int] = {}
    for r in records:
        breakdown[r.get("source", "?")] = breakdown.get(r.get("source", "?"), 0) + 1
    meta = {
        "id": sid,
        "query": query,
        "params": params,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "count": len(records),
        "sources": breakdown,
        "logs": logs,
        "corpus": str(d / "corpus.jsonl"),
    }
    (d / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return meta


def load_meta(session_id: str) -> dict | None:
    p = _dir(session_id) / "meta.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def load_corpus(session_id: str, limit: int | None = None) -> list[dict]:
    p = _dir(session_id) / "corpus.jsonl"
    if not p.exists():
        return []
    out = []
    with p.open(encoding="utf-8") as f:
        for i, line in enumerate(f):
            if limit is not None and i >= limit:
                break
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out


def list_sessions() -> list[dict]:
    if not config.SESSIONS_DIR.exists():
        return []
    metas = []
    for d in config.SESSIONS_DIR.iterdir():
        if d.is_dir():
            m = load_meta(d.name)
            if m:
                metas.append(
                    {k: m[k] for k in ("id", "query", "created_at", "count", "sources") if k in m}
                )
    metas.sort(key=lambda m: m.get("created_at", ""), reverse=True)
    return metas


def cleanup(session_id: str) -> bool:
    """Delete one session. Caller must have the user's confirmation."""
    d = _dir(session_id)
    if d.exists() and d.is_dir() and config.SESSIONS_DIR in d.parents:
        shutil.rmtree(d)
        return True
    return False


def cleanup_all() -> int:
    n = 0
    for m in list_sessions():
        if cleanup(m["id"]):
            n += 1
    return n


def seen_ids(session_id: str) -> set:
    """Record ids already captured, so a resume can skip duplicates."""
    return {r["id"] for r in load_corpus(session_id) if "id" in r}
