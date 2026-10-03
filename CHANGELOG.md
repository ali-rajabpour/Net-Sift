# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.5.0] - 2026-10-03

### Added

- Browser selection: the wizard detects installed Chromium browsers (Chrome, Edge,
  Brave, Arc, Comet, Vivaldi, Opera, Chromium) on macOS, Windows, and Linux. When
  several are present it asks which to use, remembers the choice, and opens the
  extension and login pages in that browser.
- The installer can add a net-sift line below your existing status bar instead of
  replacing it, via a wrapper that preserves and can restore the original.

### Changed

- The account check never auto-skips. For every account that is not connected it
  asks whether to connect it and, on yes, gives instructions and verifies; retries
  are user-driven, not automatic.
- The account probe retries a transient failure, so a logged-in account no longer
  reads as disconnected just because the first browser command after startup was
  flaky (fixes X intermittently showing as not connected).
- The status bar segment is shorter: `net-sift <dot><keyless>+<accounts>`.

## [0.4.2] - 2026-10-03

### Fixed

- The account check no longer loops asking you to log in when the real problem is
  that OpenCLI cannot open a site at all (a "Navigation rejected" block, seen on
  Facebook even while logged in). The probe now classifies the result: connected,
  blocked (platform/adapter block, not a login issue, reported and skipped), or a
  genuine login failure (one login attempt, then move on). No more infinite retry.

## [0.4.1] - 2026-10-03

### Fixed

- The installer no longer overwrites an existing Claude Code status bar. If one is
  already set (for example a plugin's status line), net-sift keeps it and points you
  to `net-sift status` instead of replacing it.

## [0.4.0] - 2026-10-03

### Changed

- The install wizard now checks each social account one by one in plain language
  instead of printing "walled platforms". For every account (X, Reddit, Instagram,
  Facebook, Bilibili, Xiaohongshu, Zhihu) it verifies a real search works; if an
  account is not connected it asks whether to connect it, opens the login page with
  simple steps, confirms, and moves on. Accounts you decline are skipped.
- `net-sift doctor` and the status bar now say "accounts" instead of "walled".

### Added

- `opencli.probe_login(site)` verifies a platform is actually logged in by running a
  real search and checking for an error response.

## [0.3.2] - 2026-10-03

### Fixed

- Walled platforms showed "none connected" even when OpenCLI was connected, and the
  summary could contradict itself (connected in one line, not connected in another).
  Connectivity is now checked once per report and reused, and walled platforms are
  mapped deterministically to their verified OpenCLI `search` commands
  (twitter, reddit, instagram, facebook, bilibili, xiaohongshu, zhihu) instead of
  parsing `opencli list`.

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

[Unreleased]: https://github.com/ali-rajabpour/Net-Sift/compare/v0.5.0...HEAD
[0.5.0]: https://github.com/ali-rajabpour/Net-Sift/releases/tag/v0.5.0
[0.4.2]: https://github.com/ali-rajabpour/Net-Sift/releases/tag/v0.4.2
[0.4.1]: https://github.com/ali-rajabpour/Net-Sift/releases/tag/v0.4.1
[0.4.0]: https://github.com/ali-rajabpour/Net-Sift/releases/tag/v0.4.0
[0.3.2]: https://github.com/ali-rajabpour/Net-Sift/releases/tag/v0.3.2
[0.3.1]: https://github.com/ali-rajabpour/Net-Sift/releases/tag/v0.3.1
[0.3.0]: https://github.com/ali-rajabpour/Net-Sift/releases/tag/v0.3.0
[0.2.0]: https://github.com/ali-rajabpour/Net-Sift/releases/tag/v0.2.0
[0.1.0]: https://github.com/ali-rajabpour/Net-Sift/releases/tag/v0.1.0
