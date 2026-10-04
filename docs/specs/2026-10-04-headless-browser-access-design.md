# Headless browser access via profile copy

Status: proposed
Date: 2026-10-04
Target release: 1.0.0

## Problem

Walled platforms (X, Reddit, Instagram, Facebook, Bilibili, Xiaohongshu, Zhihu)
are reached today through the OpenCLI browser-bridge extension driving the user's
live Chromium browser. That forces the browser to stay open during a sweep, and
the extension's auto-respawning daemon keeps a browser process alive, which
overheats some machines. Searches cannot run with the browser closed.

The goal is to let net-sift search both walled and open-web sources with no
browser window open, at the lowest possible UX friction, and to never leave a
browser process running after a sweep.

## What was proven first

A spike on macOS (real Google Chrome 153 and Comet, with the user logged into X,
Reddit, Instagram, Bilibili, Zhihu, Google, YouTube) established:

- OpenCLI can drive any Chromium started with `--remote-debugging-port` via
  `OPENCLI_CDP_ENDPOINT`. The extension is not required; the OpenCLI adapters are.
- A browser launched `--headless=new` with a normal (non-"Headless") user agent
  and a persistent, logged-in profile passed 8/8 tested sources, including every
  logged-in platform. A fresh profile hit Google's CAPTCHA; the logged-in profile
  did not.
- Copying a browser's own profile directory (even while that browser was running)
  and driving the **same browser binary** headless against the copy reused every
  session: 8/8. Driving a **different** binary against the copy lost half the
  sessions, because cookie values are encrypted with a per-browser key. Therefore
  reuse must stay within one browser.
- Cookie names are stored in plaintext; logged-in sites can be detected without
  decrypting anything.
- Terminating the launched process left zero residual processes every time.
- Running browser-backed sources in parallel against one endpoint failed
  ("Inspected target navigated or closed"); they must run one at a time.

## Goals

- Search with no browser window open.
- No browser process alive after a sweep; verified dead.
- Least friction: reuse sessions the user already has by copying their profile.
- Interactive login only for sites not already logged in, sequential, on explicit
  confirmation, never a storm of tabs.
- Keep every OpenCLI adapter; only the access/transport layer changes.

## Non-goals (this release)

- Windows and Linux support (macOS first; see TODO).
- Cross-browser session reuse (decrypt + re-encrypt): needs a Keychain prompt on
  macOS and is blocked by app-bound encryption on recent Windows Chrome.
- Headless support for the keyless engine sources (they use no browser).

## Architecture

```
wizard / login (headed, interactive)        search (headless, automatic)
            \                                        /
             v                                      v
        access/profile.py  --copy-->  ~/.net-sift/profiles/<browser>/
             |  detect logged-in sites (cookie names)       |
             v                                               v
        access/browsers.py (binary + profile discovery)   access/browser.py
                                                          (launch headless,
                                                           OPENCLI_CDP_ENDPOINT,
                                                           kill + verify dead)
                                                               |
                                                               v
                                                     OpenCLI adapters over CDP
                                                     (serialized, one at a time)
```

net-sift owns one managed profile per chosen browser. It is seeded by copying the
user's real profile (captures already-logged-in sites), then topped up by
interactive logins that write into the managed copy. The user's real browser is
never driven and never locked.

## Components

### access/browsers.py (new)
Detect installed Chromium browsers on macOS: display name, app bundle, executable
path, and source profile directory. Seeds from the lists already in
`installer.py`. Entry per browser:
`{id, name, executable, source_profile_dir}`.

macOS targets: Google Chrome, Comet, Brave, Microsoft Edge, Arc, Vivaldi, Opera,
Chromium. A browser counts as available only when both the executable and a
`Default` profile exist.

### access/profile.py (new)
- `copy_profile(browser) -> Path`: copy `Local State` and the needed items under
  `Default` (`Network/Cookies` or `Cookies`, `Preferences`, `Local Storage`,
  `Login Data`) into `~/.net-sift/profiles/<id>/`. Create the destination with
  `0700`; copy works while the source browser is running.
- `logged_in(profile_or_source) -> dict[str, bool]`: open the Cookies SQLite
  read-only, read cookie **names** only, map host + auth-cookie-name to a
  logged-in flag. No value is decrypted.

Auth-cookie table (host suffix -> any-of names):

| Site | Host | Auth cookie names |
|------|------|-------------------|
| x (twitter) | x.com | auth_token, ct0 |
| reddit | reddit.com | reddit_session |
| instagram | instagram.com | sessionid |
| facebook | facebook.com | c_user, xs |
| bilibili | bilibili.com | SESSDATA |
| xiaohongshu | xiaohongshu.com | web_session |
| zhihu | zhihu.com | z_c0 |
| weibo | weibo.com | SUB |
| google / youtube | google.com, youtube.com | SID, __Secure-1PSID |

### access/browser.py (new)
`managed_browser(browser_id, headed=False) -> ContextManager[str]`:

1. Pick a random free loopback port.
2. Launch the browser's own binary with `--user-data-dir=<managed copy>`,
   `--remote-debugging-port=<port>`, `--no-first-run`, `--no-default-browser-check`,
   and, when `headed=False`, `--headless=new --window-size=1280,900` plus a
   user-agent override that replaces the "HeadlessChrome" token with "Chrome".
3. Poll `http://127.0.0.1:<port>/json/version` until ready (timeout, then fail).
4. Yield `http://127.0.0.1:<port>`.
5. On exit (always): terminate, wait, `SIGKILL` if still alive, then verify no
   process remains for that `--user-data-dir`. Mirrors the Tor teardown in
   `darkweb.py`.

One managed browser per sweep. A module-level lock serializes OpenCLI calls
against the endpoint, since concurrent calls break; keyless engine sources keep
running in parallel, unaffected.

### access/opencli.py (rewrite)
- `run()` sets `OPENCLI_CDP_ENDPOINT` to the managed endpoint and drops the
  extension/daemon checks (`available`, `doctor_text`, `discover`, the
  `_parse_connected` logic).
- Keep normalization, `OPEN_SEARCH`, `WALLED_SEARCH`, `make_source`.
- `walled_sources`/`open_sources` become live whenever a managed profile exists
  for the chosen browser, not when an extension is connected.

### search.py integration
`all_sources()` builds browser-backed sources bound to the managed endpoint. A
sweep opens one `managed_browser`, runs keyless sources in the existing thread
pool and browser sources through the serializing lock, then tears the browser
down. A logged-in site returning AUTH is recorded as a gap advising
`net-sift login <site>`.

### CLI
- `net-sift install`: the wizard below.
- `net-sift login [site ...]`: open the managed profile headed and run the
  sequential login flow for the named sites (or every not-logged-in walled site).
- `net-sift doctor`: report the chosen browser, managed profile path, and per-site
  logged-in status. No extension status.
- `net-sift status`: badge reflects "profile ready / N sites" instead of
  "browser connected".

## Wizard flow (install)

1. Scan browsers. For each, show which sites are already logged in.
2. Recommend the browser with the most logged-in sites; the user confirms or picks
   another.
3. Ask consent to copy that browser's profile (state plainly that this copies
   session cookies into `~/.net-sift`). On yes, copy.
4. Re-detect logged-in sites from the copy; show the list.
5. For walled sites still not logged in that the user wants: run the sequential
   login flow.
6. Done. Searches now run headless with no further interaction.

## Login flow (sequential, headed)

For each requested site, one at a time:

1. Ask the user to confirm opening a headed window. If net-sift's managed browser
   is already open from a previous site in this flow, open a new **tab** in it
   instead of a new window.
2. Navigate to that site's login URL.
3. Poll for the site's auth cookie to appear (success) or let the user say "skip".
4. On success, continue to the next site.
5. When all requested sites are done, close the managed browser.

All logins write into net-sift's managed profile, so nothing is re-copied and the
user's real browser is never touched or locked.

## Search flow (automatic)

1. Open `managed_browser(browser_id)` headless.
2. Run the sweep (keyless parallel, browser sources serialized).
3. Tear the browser down and verify it is dead.
4. Return the usual context-lean summary.

No prompts. No window.

## Session expiry

Sessions expire. When a site known to be logged in returns AUTH at search time,
the sweep logs a gap: "session expired, run `net-sift login <site>`". No silent
re-copy in 1.0; refreshing from the real browser is a later option.

## Security

- Managed profile holds live session cookies: directory `0700`, documented
  plainly, created only on explicit consent.
- CDP endpoint bound to `127.0.0.1` on a random port, alive only for the sweep.
- Browser killed and verified dead after every sweep.
- The README line "net-sift never reads or copies browser cookies" is removed and
  replaced with an honest description of the opt-in copy.

## Removal (no fallback)

Once the CDP path is verified, delete the extension-bridge path entirely: the
daemon/extension detection in `access/opencli.py`, the extension install and
"connect your browser" steps in `installer.py`, and the OpenCLI `list`-based
adapter discovery. The OpenCLI binary stays (adapters + CDP driver). There is one
access path, not two.

## Config

| Variable | Effect |
|----------|--------|
| `NET_SIFT_BROWSER` | id of the browser whose profile to manage (else the wizard's saved choice) |
| `NET_SIFT_HOME` | unchanged; profiles live under `<home>/profiles/` |
| `NET_SIFT_OPENCLI_BIN` | unchanged |

## Testing

Unit (no browser, in CI):
- browser discovery against a mocked filesystem
- `copy_profile` into a tmp dir, permission check `0700`
- `logged_in` against a small Cookies SQLite fixture (names only)
- user-agent override builder (strips "HeadlessChrome")
- teardown verifier logic with a mocked process
- the serializing-lock path for browser sources

Manual integration (needs a real browser and real logins, kept as a script under
`scripts/`, not in CI): the source matrix from the spike, asserting that a copied
logged-in profile driven headless reaches the walled platforms and that no process
survives teardown.

## Open risks and TODO

- Windows: app-bound cookie encryption; same-browser same-user DPAPI may still
  decrypt. Untested. (TODO)
- Linux: `--headless=new` needs no Xvfb, but detection and profile paths differ.
  (TODO)
- macOS Keychain: the same-binary decrypt showed no prompt in the spike; verify on
  a clean machine during build.
- Facebook blocks automated navigation even when logged in; report honestly.
- Parallel browser sources are unsupported; serialization is required.
- Carried over, to address after this refactor: verify Brave API / GDELT /
  Marginalia live; retest OpenCLI brave/duckduckgo/36kr after the firewall check;
  logged-in checks for weibo/jike; stocktwits and github partial-failure handling.

## Migration

Breaking: users re-run `net-sift install`; the OpenCLI browser-bridge extension is
no longer needed and can be removed. Justifies the 1.0.0 version.
