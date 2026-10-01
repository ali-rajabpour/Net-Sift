---
name: net-sift
description: >
  Use for coverage-first research across social and web sources: "what is being
  said about X", "deep dive on X", "sweep every platform for X", discourse and
  sentiment surveys, competitor and topic monitoring. Covers Bluesky, Hacker News,
  GitHub, arXiv, Polymarket, StockTwits, Mastodon, and more without login, plus
  Twitter/X, Reddit, Instagram, Facebook, Bilibili, and Xiaohongshu through the
  user's logged-in Chromium browser (OpenCLI). Not for writing reports, posting, or
  single-link lookups.
---

# Net-Sift

Net-Sift is an MCP server. Call its tools; do not reinvent the retrieval.

## Tools

- `deep_search(query, platforms?, since?, until?, max_budget?, rank?)` runs the
  sweep. It writes the full corpus to disk and returns only a summary: record
  counts per source, a coverage map, the gap list, the top ranked items, and the
  corpus path. Read the summary, not a raw dump.
- `doctor(probe?)` reports what is reachable and how to connect walled platforms.
- `status()` is a compact connectivity snapshot.
- `list_sessions()`, `resume(session_id)`, `cleanup(session_id)` manage saved
  searches.
- `fetch(url)` returns readable text for one page.

## Rules

1. Run `doctor` first when the task needs a walled platform (X, Reddit, Instagram,
   Facebook, Bilibili, Xiaohongshu). If it is not connected, tell the user to open
   a Chromium browser with the OpenCLI extension and log in, then stop.
2. Pass the results to the user as findings. The gap list is part of the answer:
   name what could not be reached and why.
3. After a finished search, tell the user the corpus is saved and ask whether to
   keep it for a later `resume` or delete it with `cleanup`. Never delete without
   their confirmation.
4. Recency is a ranking boost, not a hard window. `since`/`until` bound retrieval;
   old on-topic items still surface.
