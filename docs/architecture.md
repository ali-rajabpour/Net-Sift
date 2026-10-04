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

- `browsers.py` discovers installed Chromium browsers (executable + source profile).
- `profile.py` copies a chosen browser's profile into `~/.net-sift/profiles/<id>/`
  (0700) and detects logged-in sites by reading cookie names only; cookie values are
  never decrypted, so the copy is only ever driven by its own browser binary.
- `browser.py` launches that browser headless over CDP with a random loopback
  debugging port, and kills and verifies it dead when the sweep ends.
- `opencli.py` drives the managed browser by setting `OPENCLI_CDP_ENDPOINT` and
  shelling to `opencli <site> <command> -f json`, serialized so concurrent calls do
  not crash the shared page. Output is normalized into the record shape, so the raw
  payload never reaches the agent. Walled and web source maps are verified constants,
  not runtime discovery.

## Server and surface

- `search.py` merges keyless sources with the browser-backed adapters, opens one
  managed headless browser for the sweep when any are selected, runs it, saves a
  session, and returns a summary.
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
- One path per environment, no silent fallbacks. Walled and web sources need a
  managed browser profile; where that is absent they are a declared gap.
- Recency is a ranking boost, never a hard window.
