# Connecting walled platforms with OpenCLI

Net-Sift reaches login-walled platforms (Twitter/X, Reddit, Instagram, Facebook,
Bilibili, Xiaohongshu, Zhihu, Weibo) and general web search by driving a headless
Chromium with [OpenCLI](https://github.com/jackwener/opencli). The browser is one
net-sift launches itself from a copy of your logged-in profile, so searches run with
your normal browser closed and no browser process is left running. Keyless sources
(Bluesky, Hacker News, GitHub, arXiv, and the rest) need none of this.

macOS only for now. `net-sift install` does all of the below; this is the manual path.

## 1. Install Node and OpenCLI

OpenCLI needs Node.js 20.18.1 or newer and provides the site adapters net-sift drives.

```bash
npm install -g @jackwener/opencli
```

No browser extension is required: net-sift talks to the browser over the DevTools
protocol, not through the OpenCLI bridge extension.

## 2. Use a Chromium browser

Chrome, Comet, Brave, Edge, or Arc. Safari and Firefox do not work. Log into the
platforms you want in that browser as you normally would.

## 3. Copy the profile

```bash
net-sift install        # detects your browsers, shows what each is logged into,
                        # and copies the one you pick into ~/.net-sift/profiles/
net-sift login reddit   # log into anything you are not already signed into
```

The copy holds your session cookies and lives under `~/.net-sift/profiles/` with
`0700` permissions. It stays on your machine and is never uploaded. Because cookies
are encrypted with a per-browser key, the copy is only ever driven by the same
browser it came from.

## 4. Verify

```bash
net-sift doctor
```

It shows the chosen browser, whether the managed profile is ready, and which accounts
are signed in. The status bar (after `net-sift install`) shows the same at a glance.

## Notes

- Keep requests spaced out. High-frequency sweeps can trigger platform rate limits
  or captchas that no tool can bypass.
- Sessions expire. When a site that was signed in starts returning an auth error,
  re-run `net-sift login <site>`.
