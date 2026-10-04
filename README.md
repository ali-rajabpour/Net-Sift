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
the answer, not an afterthought. Login-walled platforms are reached through your
own logged-in Chromium browser, so there is no cookie copying and no private-API
reverse engineering.

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
  Zhihu) through your logged-in Chromium browser via OpenCLI.
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
- A guided installer that picks your browser, checks each account, and adds a
  `[NET-SIFT]` status line.

## How it works

```
query
  |
  v
sources (keyless)          access (walled, via OpenCLI + your browser)
  \_________________  _________________/
                    \/
         gap-closing driver (bisect on ceiling)
                    |
            dedup + ranking
                    |
         session on disk  --->  summary + coverage + gaps  --->  agent
```

Keyless sources call public endpoints directly. Walled platforms are reached by
shelling to `opencli <site> <command>` against your logged-in browser. Results are
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
- detects your Chromium browsers and, if you have more than one, asks which to use,
  then opens the extension and login pages in it;
- checks each walled account one by one and, for any that is not connected, asks
  whether to connect it and walks you through logging in;
- offers the optional extras: Tor (for dark-web discussion search) and a HikerAPI
  key (for Instagram account recon).

Every step asks before it changes anything. Restart your client afterward so it
picks up the server.

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

Twitter/X, Reddit, Instagram, Facebook, Bilibili, Xiaohongshu, and Zhihu need a
logged-in Chromium browser and OpenCLI. `net-sift install` handles most of this;
see [net_sift/guides/setup-opencli.md](net_sift/guides/setup-opencli.md) for the
manual version:

1. Install Node 20.18.1+ and `@jackwener/opencli` (or OpenCLIApp).
2. Use a Chromium browser (Chrome, Edge, Brave, Arc, Comet, and so on) with the
   OpenCLI Browser Bridge extension. Safari and Firefox cannot load it.
3. Log into the platforms you want in that browser.
4. Run `net-sift doctor` to confirm.

Desktop only. There is no headless or server path for walled platforms. Some
platforms (for example Facebook) block automated navigation even when you are
logged in; net-sift reports that honestly and moves on rather than looping.

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
sources are on by default; walled sources appear once OpenCLI is connected.

## MCP tools

| Tool | Purpose |
|------|---------|
| `deep_search` | run a sweep, return a summary and the corpus path |
| `resume` | continue an earlier search |
| `list_sessions` | list saved searches |
| `cleanup` | delete a saved search (after user confirmation) |
| `doctor` | what is reachable and how to connect walled platforms |
| `status` | compact connectivity snapshot |
| `darkweb_search` | read-only, information-only Tor onion-forum discussion search (opt-in, needs Tor) |
| `instagram_recon` | per-account Instagram analysis via HikerAPI (opt-in, metered, needs a key) |

## Configuration

| Variable | Effect |
|----------|--------|
| `GITHUB_TOKEN` | higher GitHub Search API rate limit |
| `BRAVE_API_KEY` | enables the Brave Search API web source (metered) |
| `MARGINALIA_API_KEY` | personal Marginalia key; adds `marginalia` to the default sweep |
| `HIKERAPI_KEY` | enables Instagram account recon |
| `NET_SIFT_HOME` | session storage location (default `~/.net-sift`) |
| `NET_SIFT_OPENCLI_BIN` | path to the `opencli` binary if not on `PATH` |

Keys are read from the environment first. The only credential net-sift persists is
an optional HikerAPI key you supply in the wizard, saved to
`~/.net-sift/secrets.json` with 0600 permissions. Walled platforms use your own
browser session; net-sift never reads or copies browser cookies.

## Sessions and privacy

Each search is written to `~/.net-sift/sessions/<id>/` as `corpus.jsonl` and
`meta.json`. Nothing is sent anywhere. After a search, Net-Sift reminds you the
corpus is kept so you can `resume` it, and deletes it only when you call `cleanup`.
Walled platforms use your own browser session; Net-Sift never reads or copies your
cookies.

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
