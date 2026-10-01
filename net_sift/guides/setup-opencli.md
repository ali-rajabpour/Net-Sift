# Connecting walled platforms with OpenCLI

Net-Sift reaches login-walled platforms (Twitter/X, Reddit, Instagram, Facebook,
Bilibili, Xiaohongshu) through your own logged-in Chromium browser using
[OpenCLI](https://github.com/jackwener/opencli). Nothing is scraped behind your
back: OpenCLI reuses the browser session you already control. Keyless sources
(Bluesky, Hacker News, GitHub, arXiv, and the rest) need none of this.

Desktop only. There is no headless or server path for walled platforms.

## 1. Install Node and OpenCLI

OpenCLI needs Node.js 20.18.1 or newer.

```bash
npm install -g @jackwener/opencli
# or install OpenCLIApp, which bundles the runtime and a tray UI
```

## 2. Use a Chromium browser

OpenCLI connects through a browser-bridge extension, which loads in Chromium-family
browsers only: Chrome, Chromium, Edge, Brave, Arc, Opera, Vivaldi, Comet. Safari
and Firefox cannot load the extension.

Install the OpenCLI Browser Bridge extension in that browser and keep the browser
open.

## 3. Log into the platforms you want

Open each platform (x.com, reddit.com, and so on) in that browser and sign in as
normal. OpenCLI uses those sessions. Net-Sift never reads or copies your cookies.

## 4. Verify

```bash
net-sift doctor
```

It lists which walled platforms are connected. If none are, it tells you exactly
what is missing. The status bar (after `net-sift install`) shows the same at a
glance.

## Notes

- Keep requests spaced out. High-frequency sweeps can trigger platform rate limits
  or captchas that no tool can bypass.
- Each Chrome profile runs its own extension instance. With several profiles, pick
  one with `opencli profile use <alias>`.
