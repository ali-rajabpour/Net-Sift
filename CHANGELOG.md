# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.1] - 2026-10-03

### Fixed

- The install wizard now starts the OpenCLI daemon itself. OpenCLI's daemon only
  starts when an opencli command runs, so the browser extension stayed at
  "reconnecting" and the wizard never detected it. Connectivity is now determined
  by running `opencli doctor` (which starts the daemon and reports status) instead
  of an unverified status port, and the status bar caches the result.

## [0.3.0] - 2026-10-03

### Changed

- Relicensed from MIT to GNU AGPL-3.0-or-later. Adapted Agent Reach code remains
  under its original MIT terms, attributed in NOTICE.

### Added

- Project banner at the top of the README.



### Changed

- `net-sift install` is now a guided wizard. It registers with the clients it
  detects, installs OpenCLI automatically through npm (with consent), and walks the
  user through connecting a Chromium browser, rechecking as it goes. Each step asks
  before acting and reports exactly what is needed on failure instead of leaving a
  bare warning. Add `--yes` for an unattended run.

## [0.1.0] - 2026-10-01

### Added

- Coverage-first search engine: keyless sources (Bluesky, Hacker News, GitHub,
  arXiv, Polymarket, StockTwits, Mastodon, Habr, V2EX, Telegram, Sogou WeChat),
  a window-bisecting gap-closing driver, per-source near-duplicate dedup, and
  relevance ranking with head-entity grounding, CJK segmentation, a recency boost,
  and engagement weighting.
- Walled-platform access (Twitter/X, Reddit, Instagram, Facebook, Bilibili,
  Xiaohongshu) through the user's logged-in Chromium browser via OpenCLI, with
  runtime adapter discovery.
- MCP server exposing `deep_search`, `resume`, `list_sessions`, `cleanup`,
  `doctor`, `status`, and `fetch`, all context-lean.
- Session storage under `~/.net-sift/sessions/` with keep-or-delete confirmation.
- `net-sift` CLI: `install`, `serve`, `doctor`, `status`, `search`.
- Installer that registers the MCP server and status bar for Claude Code and Codex.
- Test suite, Ruff linting, and GitHub Actions CI.

[Unreleased]: https://github.com/ali-rajabpour/Net-Sift/compare/v0.3.1...HEAD
[0.3.1]: https://github.com/ali-rajabpour/Net-Sift/releases/tag/v0.3.1
[0.3.0]: https://github.com/ali-rajabpour/Net-Sift/releases/tag/v0.3.0
[0.2.0]: https://github.com/ali-rajabpour/Net-Sift/releases/tag/v0.2.0
[0.1.0]: https://github.com/ali-rajabpour/Net-Sift/releases/tag/v0.1.0
