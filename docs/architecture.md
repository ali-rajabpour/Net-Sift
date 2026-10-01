# Architecture

Net-Sift has three layers: an engine, an access layer, and an MCP server.

## Engine (`net_sift/engine/`)

Stdlib-only, so it installs anywhere as plain Python.

- `core.py` holds the HTTP transport (paced, retrying), the record shape (`rec`),
  per-source near-duplicate dedup, the gap-closing driver (`collect`), and the
  `run` orchestrator.
- `sources.py` holds the keyless sources. Each is a callable
  `(query, since, until, budget) -> (records, hit_ceiling)`.
- `ranking.py` scores records by relevance (phrase and token overlap, CJK-aware)
  with head-entity grounding, then modulates by a recency boost and engagement.

A source returns `hit_ceiling=True` when it cannot page further. `collect` then
bisects the time window and re-queries each half, recovering the tail. The gap
report records anything that still could not be reached.

## Access (`net_sift/access/`)

- `opencli.py` reaches walled login platforms through the user's logged-in
  Chromium browser via OpenCLI. Adapters are discovered at runtime with
  `opencli list`; net-sift shells to `opencli <site> <command> -f json` and
  normalizes the output into the same record shape, so the raw payload never
  reaches the agent.

## Server and surface

- `search.py` merges keyless sources with any connected walled adapters, runs the
  sweep, saves a session, and returns a summary.
- `sessions.py` stores each search under `~/.net-sift/sessions/<id>/` as
  `corpus.jsonl` plus `meta.json`. The corpus is kept until the user confirms a
  delete.
- `mcp_server.py` exposes the tools. Every tool is context-lean: it returns
  summaries, paths, errors, and questions, never the raw corpus.
- `doctor.py` and `status.py` report what is reachable.
- `cli.py` serves the MCP, runs the doctor, prints status, and installs the server
  and status bar into Claude Code and Codex.

## Design rules

- Read-only: no posting, commenting, liking, or auth bypass.
- One path per environment, no silent fallbacks. Walled platforms need a desktop
  Chromium session; where that is absent they are a declared gap.
- Recency is a ranking boost, never a hard window.
