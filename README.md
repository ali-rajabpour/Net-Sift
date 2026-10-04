<p align="center">
  <img src="https://raw.githubusercontent.com/ali-rajabpour/Net-Sift/main/docs/assets/banner.png" alt="Net-Sift" width="100%">
</p>

<p align="center">
  <a href="https://github.com/ali-rajabpour/Net-Sift/actions/workflows/ci.yml"><img src="https://github.com/ali-rajabpour/Net-Sift/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/net-sift/"><img src="https://img.shields.io/pypi/v/net-sift.svg" alt="PyPI"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-AGPL%20v3-blue.svg" alt="License: AGPL v3"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.10%2B-green.svg" alt="Python 3.10+"></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/badge/lint-ruff-261230.svg" alt="Linting: Ruff"></a>
</p>

Net-Sift sweeps many sources for everything being said about a topic, ranks it,
removes duplicates, and reports what it could not reach. The gap report is part of
the answer, not an afterthought. Login-walled platforms are reached by copying your
own Chromium profile and driving it headless, so searches run with the browser
closed and no browser process is left running.

## Table of contents

- [Why Net-Sift](#why-net-sift)
- [Features](#features)
- [How it works](#how-it-works)
- [Install](#install)
- [Quickstart](#quickstart)
- [Walled platforms](#walled-platforms)
- [Optional features](#optional-features)
- [Sources](#sources)
- [MCP tools](#mcp-tools)
- [Configuration](#configuration)
- [Sessions and privacy](#sessions-and-privacy)
- [Development](#development)
- [Contributing](#contributing)
- [Security](#security)
- [License](#license)
- [Acknowledgements](#acknowledgements)

## Why Net-Sift

Most research tools return a handful of links or a synthesized answer. Net-Sift
returns a corpus with an explicit account of coverage: what was retrieved, what hit
a ceiling, and what was out of reach. It is built for topic surveys, sentiment
sweeps, competitor and discourse monitoring, and literature-style scans where a
single search would under-serve the answer.

## Features

- Many sources in one sweep, keyless by default (Bluesky, Hacker News, GitHub,
  arXiv, Polymarket, StockTwits, Mastodon, and more).
- Walled platforms (Twitter/X, Reddit, Instagram, Facebook, Bilibili, Xiaohongshu,
  Zhihu) and general web search, run headless from a copy of your logged-in
  Chromium profile via OpenCLI, with the browser closed.
- Relevance ranking with head-entity grounding, CJK-aware tokenization, a recency
  boost, and engagement weighting.
- A gap-closing driver that bisects the time window to recover tails a source
  would otherwise hide.
- Per-source near-duplicate collapse, so repeats do not inflate the corpus while
  cross-platform coverage is preserved.
- Context-lean by design: the agent receives summaries, coverage, gaps, and the
  top results, never the raw corpus.
- Saved sessions you can continue later, deleted only on your confirmation.
- Opt-in extras: dark-web discussion search (Tor, read-only and information-only)
  and per-account Instagram recon (HikerAPI).
- A guided installer that copies your browser profile, logs you into any missing
  accounts one at a time, and adds a `[NET-SIFT]` status line.

## How it works

```
query
  |
  v
sources (keyless)       access (walled + web, OpenCLI over a managed headless browser)
  \_________________  _________________/
                    \/
         gap-closing driver (bisect on ceiling)
                    |
            dedup + ranking
                    |
         session on disk  --->  summary + coverage + gaps  --->  agent
```

Keyless sources call public endpoints directly. Walled and web sources run through
`opencli <site> <command>` pointed at a headless Chromium that net-sift launches from
a copy of your logged-in profile, then kills when the sweep ends. Results are
normalized to one record shape, deduplicated, ranked, and written to a session.
Only the summary returns to the caller.

## Install

```bash
uv tool install net-sift        # or: pipx install net-sift
```

Then run the setup wizard:

```bash
net-sift install                # guided; add --yes for unattended
```

`net-sift install` is a wizard. It:

- registers the MCP server and a status bar with the clients it finds (Claude Code,
  Codex), adding a `[NET-SIFT]` line below any status bar you already have rather
  than replacing it;
- installs OpenCLI through npm with your consent;
- detects your Chromium browsers, shows which sites each is already logged into, and,
  with your consent, copies the one you pick into net-sift's managed area so searches
  can run with the browser closed;
- offers to log into any walled site you are not already signed into, one at a time,
  in a window net-sift opens;
- offers the optional extras: Tor (for dark-web discussion search) and a HikerAPI
  key (for Instagram account recon).

Every step asks before it changes anything. Add an account later with
`net-sift login <site>`. Restart your client afterward so it picks up the server.

macOS only for now; Windows and Linux are planned.

## Quickstart

```bash
net-sift doctor               # what can be reached right now
net-sift search "topic" --platforms github,arxiv --max 50
```

In an MCP client, call `deep_search`:

```
deep_search(query="post-quantum cryptography adoption", since="2026-01-01")
```

You get a summary with per-source counts, a coverage map, the gap list, the top
ranked items, and the corpus path.

## Walled platforms

Twitter/X, Reddit, Instagram, Facebook, Bilibili, Xiaohongshu, and Zhihu need
OpenCLI and a managed browser profile. `net-sift install` handles this; see
[net_sift/guides/setup-opencli.md](net_sift/guides/setup-opencli.md) for the manual
version:

1. Install Node 20.18.1+ and `@jackwener/opencli`.
2. Use a Chromium browser (Chrome, Comet, Brave, Edge, Arc). Safari and Firefox do
   not work.
3. `net-sift install` copies that browser's logged-in profile into net-sift's
   managed area; `net-sift login <site>` logs you into anything you have not signed
   into yet.
4. Run `net-sift doctor` to confirm.

Searches then run headless from the copied profile, with the browser closed; net-sift
kills the browser when the sweep ends. macOS only for now. Some platforms (for example
Facebook) block automated navigation even when you are logged in; net-sift reports
that honestly and moves on rather than looping.

## Optional features

- **Dark-web discussion search** (`darkweb_search`): read-only, information-only
  search across Tor onion forums, with a non-optional filter that drops markets,
  credentials, drugs, weapons, and abuse. Needs `tor`; net-sift starts and stops
  its own ephemeral Tor. `net-sift install` offers to set it up.
- **Instagram account recon** (`instagram_recon`): profile, timeline, posting
  locations, top engagers, followers, and shared-follower intersection via
  HikerAPI. Metered and opt-in; the wizard stores your key at
  `~/.net-sift/secrets.json` (0600), or set `HIKERAPI_KEY` in the environment.

## Sources

Full table in [net_sift/guides/sources.md](net_sift/guides/sources.md). Keyless
sources are on by default; walled and web sources become available once a managed
browser profile exists.

## MCP tools

| Tool | Purpose |
|------|---------|
| `deep_search` | run a sweep, return a summary and the corpus path |
| `resume` | continue an earlier search |
| `list_sessions` | list saved searches |
| `cleanup` | delete a saved search (after user confirmation) |
| `doctor` | what is reachable, the managed browser, and which accounts are signed in |
| `status` | compact connectivity snapshot |
| `darkweb_search` | read-only, information-only Tor onion-forum discussion search (opt-in, needs Tor) |
| `instagram_recon` | per-account Instagram analysis via HikerAPI (opt-in, metered, needs a key) |

## Configuration

| Variable | Effect |
|----------|--------|
| `GITHUB_TOKEN` | higher GitHub Search API rate limit |
| `BRAVE_API_KEY` | enables the keyed `brave_api` source (keyless `brave` runs through the browser) |
| `MARGINALIA_API_KEY` | personal Marginalia key; adds `marginalia` to the default sweep |
| `CONTEXT7_API_KEY` | enables Context7 code and library documentation search |
| `HIKERAPI_KEY` | enables Instagram account recon |
| `NET_SIFT_HOME` | session storage location (default `~/.net-sift`) |
| `NET_SIFT_OPENCLI_BIN` | path to the `opencli` binary if not on `PATH` |

| `NET_SIFT_BROWSER` | id of the browser to manage (overrides the wizard's choice) |

Keys are read from the environment first. net-sift persists an optional HikerAPI key
(`~/.net-sift/secrets.json`, 0600) and, with your consent during `net-sift install`, a
copy of your chosen browser's profile under `~/.net-sift/profiles/` (0700). That copy
holds session cookies so walled and web sources can run with the browser closed; it
stays on your machine and is never uploaded.

## Sessions and privacy

Each search is written to `~/.net-sift/sessions/<id>/` as `corpus.jsonl` and
`meta.json`. Nothing is sent anywhere. After a search, Net-Sift reminds you the
corpus is kept so you can `resume` it, and deletes it only when you call `cleanup`.
Walled and web sources use a copy of your browser profile that stays on your machine
under `~/.net-sift/profiles/` (0700); it is never uploaded.

## Development

```bash
git clone https://github.com/ali-rajabpour/Net-Sift.git
cd Net-Sift
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
ruff check net_sift tests && pytest
```

See [docs/architecture.md](docs/architecture.md) for the design.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Net-Sift is read-only research: it does not
post, comment, or bypass authentication, and contributions stay within that scope.

## Security

See [SECURITY.md](SECURITY.md). Report vulnerabilities privately through GitHub.

## License

GNU AGPL-3.0-or-later. See [LICENSE](LICENSE). If you run a modified version as a
network service, the AGPL requires you to offer users its source. This project
includes code adapted from [Agent Reach](https://github.com/Panniantong/Agent-Reach)
(MIT, a permissive license compatible with AGPL); that attribution is kept in
[NOTICE](NOTICE).

## Acknowledgements

- [OpenCLI](https://github.com/jackwener/opencli) for logged-in browser access.
- [Agent Reach](https://github.com/Panniantong/Agent-Reach) for the onboarding and
  doctor patterns.
