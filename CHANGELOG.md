# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres
to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.1.0] - 2026-10-04

### Added

- `brave` and `duckduckgo`: keyless general web search through the managed headless
  browser. Both are independent of Google and are not CAPTCHA-blocked the way Google
  web search is, so they are the reliable general-web sources.
- `context7`: up-to-date code and library documentation search (keyed,
  `CONTEXT7_API_KEY`).

### Changed

- The keyed Brave Search API source is now `brave_api` (used when there is no managed
  profile); keyless `brave` runs through the browser.
- The install-time source check now classifies Google's CAPTCHA block as "blocked"
  rather than a bare error, and does not offer a pointless login for it.

## [1.0.0] - 2026-10-04

### Added

- Headless browser access: net-sift launches its own Chromium headless over the
  DevTools protocol from a copy of your logged-in profile, so walled and web sources
  run with your browser closed. The browser is killed and verified dead after every
  sweep, so nothing is left running.
- `net-sift install` now detects your Chromium browsers, shows which sites each is
  signed into, copies the one you choose into `~/.net-sift/profiles/<id>/` (0700),
  and offers to log into any missing walled site, one at a time.
- `net-sift login [sites]`: open the managed profile and sign into walled platforms.
- `net-sift install` ends with a live source check: it runs every walled and web
  source once from the copied profile, reports which connect and which do not, and
  offers to log into the ones a login can fix. Also available as `net-sift verify`.
- Session detection by cookie name (no values decrypted) in `doctor` and `status`.
- General web search: `google` through the managed browser, and `brave` through
  the Brave Search API when `BRAVE_API_KEY` is set (capped at 10 requests and 200
  results per sweep, never bisected).
- News: `gdelt` (keyless, 65 languages, bisected by date), `google_news`, `reuters`.
- Video and audio: `youtube`, `tiktok`, `apple_podcasts`.
- Long-form: `substack`, `medium`. Small web: `marginalia`.
- Reference and archive: `stackoverflow`, `wikipedia`, `wikidata`, `archive`.
- Chinese: `weixin`, `tieba`.
- Telegram channel discovery: with the managed browser open, the sweep finds public
  channels for the query through Google and reads them, so `telegram` no longer
  needs a hand-written channel list.

### Changed

- Walled and web sources now require a managed browser profile instead of a live
  browser with the OpenCLI bridge extension. `doctor` and `status` report the chosen
  browser, whether the profile is ready, and which accounts are signed in.
- macOS only this release; Windows and Linux are planned.

### Removed

- The OpenCLI browser-bridge extension path and its daemon/extension connectivity
  checks. net-sift drives the browser directly over CDP; the extension is no longer
  installed or required.

### Fixed

- `telegram` reported a ceiling on every call, so the driver fetched the same
  channel pages up to 127 times per sweep. It now fetches each channel once.
- `sogou_wechat` had the same always-ceiling fault and repeated one request up to
  127 times, which also tripped its captcha. A block is now one declared gap.
- `github` ignored the date window and treated a rate limit as a ceiling, so it
  re-ran identical queries while rate limited. It now searches inside the window
  (`pushed:` for repositories, `updated:` for issues) and reports a failure as a gap.
- `telegram` now drops posts outside the date window.
- `polymarket` reported a failed request as zero records instead of a gap.
- Request pacing used one lock for all hosts, so a slow host stalled every other
  source. Pacing is now per host.
- OpenCLI counts and epochs that arrive as strings (`"2,567,631 views"`) are now
  parsed, so engagement and dates reach the ranker.
- An OpenCLI adapter that finds nothing is an empty result, not a failed source.

## [0.6.2] - 2026-10-04

### Removed

- The generic `fetch` MCP tool. Making an arbitrary-URL fetcher fully SSRF-safe
  (redirect bypass, DNS-rebinding TOCTOU, unbounded reads) is not worth the attack
  surface for a search-first tool; use your client's own web fetch instead. This
  removes that entire class of findings.

### Fixed

- `secrets.json` permissions are re-applied to 0600 even when the file already
  existed with looser bits.

## [0.6.1] - 2026-10-04

### Security

- `secrets.json` is created with 0600 permissions from the start (os.open), so a
  saved key is never briefly world-readable.
- The `fetch` tool refuses private, loopback, link-local, and reserved addresses
  (SSRF guard) and marks returned page content as untrusted.
- `instagram_recon` clamps the per-call billed-request cap to 1000 so a caller
  cannot spend without bound.

## [0.6.0] - 2026-10-04

### Added

- Dark-web discussion search (`darkweb_search` MCP tool): read-only,
  information-only search across Tor onion forums, with a non-optional content
  filter (markets, credentials, drugs, weapons, abuse are dropped) and a
  self-managed ephemeral Tor that is started and verifiably torn down per call.
  Opt-in; needs `tor` installed.
- Instagram account recon (`instagram_recon` MCP tool): profile, timeline, where,
  fans, followers, intersect via HikerAPI, each capped at a per-request budget.
  Opt-in; the key is set during `net-sift install` (or env `HIKERAPI_KEY`) and
  saved to `~/.net-sift/secrets.json` with 0600 permissions.
- Wizard "Optional features" step offering Tor install and a HikerAPI key.
- `net-sift doctor` reports dark-web (Tor) and Instagram-recon (key) availability.

### Changed

- The status bar badge is now a colored `[NET-SIFT]` (blue when a browser is
  connected, red when not).

## [0.5.1] - 2026-10-04

### Changed

- The status bar line is now informative: `net-sift ● 7 social + 11 web sources
  ready`, or `net-sift ○ browser not connected · 11 web sources ready`, instead of
  the bare `net-sift 11+7`.

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

[Unreleased]: https://github.com/ali-rajabpour/Net-Sift/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/ali-rajabpour/Net-Sift/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/ali-rajabpour/Net-Sift/compare/v0.6.2...v1.0.0
[0.6.2]: https://github.com/ali-rajabpour/Net-Sift/releases/tag/v0.6.2
[0.6.1]: https://github.com/ali-rajabpour/Net-Sift/releases/tag/v0.6.1
[0.6.0]: https://github.com/ali-rajabpour/Net-Sift/releases/tag/v0.6.0
[0.5.1]: https://github.com/ali-rajabpour/Net-Sift/releases/tag/v0.5.1
[0.5.0]: https://github.com/ali-rajabpour/Net-Sift/releases/tag/v0.5.0
[0.4.2]: https://github.com/ali-rajabpour/Net-Sift/releases/tag/v0.4.2
[0.4.1]: https://github.com/ali-rajabpour/Net-Sift/releases/tag/v0.4.1
[0.4.0]: https://github.com/ali-rajabpour/Net-Sift/releases/tag/v0.4.0
[0.3.2]: https://github.com/ali-rajabpour/Net-Sift/releases/tag/v0.3.2
[0.3.1]: https://github.com/ali-rajabpour/Net-Sift/releases/tag/v0.3.1
[0.3.0]: https://github.com/ali-rajabpour/Net-Sift/releases/tag/v0.3.0
[0.2.0]: https://github.com/ali-rajabpour/Net-Sift/releases/tag/v0.2.0
[0.1.0]: https://github.com/ali-rajabpour/Net-Sift/releases/tag/v0.1.0
