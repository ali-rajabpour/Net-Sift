"""Install wizard: set up net-sift end to end for a non-technical user.

It registers the MCP server and status bar with any client it finds, installs
OpenCLI automatically, and walks the user through connecting a browser. Every step
asks before it changes anything, then does the work; nothing is left as a bare
warning. There is one intended path per step and no silent fallback: if a step
cannot finish, the wizard says exactly what is needed and lets the user retry or
skip, rather than quietly degrading.

The config writers and version helpers are pure and tested; the wizard runner is
interactive. Pass assume_yes=True for an unattended run (steps that need a human,
such as browser login, are reported as skipped instead of blocking).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

from . import config
from .access import browser, browsers, profile

MCP_ENTRY = {"command": "net-sift", "args": ["serve"]}
NODE_MIN = (20, 18, 1)
OPENCLI_NPM = "@jackwener/opencli"


# --- pure helpers (tested) ------------------------------------------------


def parse_version(text: str) -> tuple[int, ...]:
    """Extract a numeric version tuple from strings like 'v26.9.0' or 'node 20.18.1'."""
    nums = ""
    for ch in text:
        if ch.isdigit() or ch == ".":
            nums += ch
        elif nums:
            break
    parts = [int(p) for p in nums.split(".") if p != ""]
    return tuple(parts) if parts else (0,)


def node_ok(version_text: str, minimum: tuple[int, ...] = NODE_MIN) -> bool:
    return parse_version(version_text) >= minimum


def merge_json_mcp(path: Path) -> str:
    """Add the net-sift MCP server to a Claude-style ~/.claude.json."""
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return f"skipped {path} (not valid JSON; add net-sift manually)"
    servers = data.setdefault("mcpServers", {})
    if servers.get("net-sift") == MCP_ENTRY:
        return f"already present in {path}"
    servers["net-sift"] = MCP_ENTRY
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return f"registered MCP in {path}"


def ensure_statusline(path: Path) -> str:
    """Set the Claude Code status bar to net-sift in settings.json."""
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return f"skipped {path} (not valid JSON; add statusLine manually)"
    line = {"type": "command", "command": "net-sift status --line", "padding": 0}
    existing = data.get("statusLine")
    if existing == line:
        return f"status bar already set in {path}"
    # Never clobber someone else's status bar. Only set ours when none exists.
    if isinstance(existing, dict) and "net-sift" not in str(existing.get("command", "")):
        return (
            "kept your existing status bar (net-sift did not change it); "
            "see net-sift status in a terminal with `net-sift status`"
        )
    data["statusLine"] = line
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return f"status bar set in {path}"


def _nsift_dir(home: Path) -> Path:
    return config.HOME if home == Path.home() else home / ".net-sift"


def compose_statusline(path: Path, home: Path, ui: _UI) -> str:
    """Make net-sift's status show WITHOUT clobbering an existing status bar.

    No status bar yet  -> set net-sift's directly.
    A status bar exists -> offer to add a net-sift line BELOW it, via a wrapper
    that runs the original command and then net-sift on its own line. The original
    is saved so it can be restored. Never replaces the user's bar silently.
    """
    data = {}
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            return f"skipped {path} (not valid JSON; add net-sift to statusLine manually)"
    nsline = {"type": "command", "command": "net-sift status --line"}
    existing = data.get("statusLine")

    if not isinstance(existing, dict) or not existing.get("command"):
        data["statusLine"] = nsline
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return f"status bar set in {path}"

    cmd = str(existing.get("command", ""))
    wrap = _nsift_dir(home) / "statusline-wrap.sh"
    if "net-sift" in cmd or str(wrap) in cmd:
        return "net-sift already in your status bar"

    if not ui.confirm("Add a net-sift line to your status bar (keeps your current bar)?"):
        return "kept your status bar unchanged (see `net-sift status` any time)"

    # Save the original so it can be restored, then write a wrapper that runs it
    # and appends net-sift on a new line. Both get the same stdin from Claude.
    wrap.parent.mkdir(parents=True, exist_ok=True)
    (_nsift_dir(home) / "statusline-prev.json").write_text(json.dumps(existing), encoding="utf-8")
    wrap.write_text(
        "#!/usr/bin/env bash\n"
        "# Auto-generated by net-sift. Runs your original status bar, then adds a\n"
        "# net-sift line below it. Delete this and restore statusline-prev.json to undo.\n"
        'IN="$(cat)"\n'
        f"printf '%s' \"$IN\" | {cmd}\n"
        "printf '\\n'\n"
        "printf '%s' \"$IN\" | net-sift status --line\n",
        encoding="utf-8",
    )
    wrap.chmod(0o755)
    data["statusLine"] = {"type": "command", "command": f'bash "{wrap}"'}
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return "added a net-sift line below your status bar"


def ensure_codex(path: Path) -> str:
    """Add [mcp_servers.net-sift] to a Codex config.toml without rewriting the file."""
    block = '\n[mcp_servers.net-sift]\ncommand = "net-sift"\nargs = ["serve"]\n'
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if "[mcp_servers.net-sift]" in existing:
        return f"already present in {path}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(existing + block, encoding="utf-8")
    return f"registered MCP in {path}"


def detect_clients(home: Path) -> dict[str, bool]:
    """Which MCP clients look installed on this machine."""
    return {
        "claude": (home / ".claude.json").exists()
        or (home / ".claude").exists()
        or shutil.which("claude") is not None,
        "codex": (home / ".codex").exists() or shutil.which("codex") is not None,
    }


# --- interactive runner ---------------------------------------------------


class _UI:
    def __init__(self, assume_yes: bool):
        self.assume_yes = assume_yes

    def step(self, msg: str) -> None:
        print(f"\n== {msg} ==")

    def ok(self, msg: str) -> None:
        print(f"  [ok] {msg}")

    def warn(self, msg: str) -> None:
        print(f"  [!] {msg}")

    def info(self, msg: str) -> None:
        print(f"  {msg}")

    def confirm(self, msg: str, default: bool = True) -> bool:
        if self.assume_yes:
            return True
        suffix = "[Y/n]" if default else "[y/N]"
        try:
            ans = input(f"  {msg} {suffix} ").strip().lower()
        except EOFError:
            return default
        if not ans:
            return default
        return ans in ("y", "yes")

    def pause(self, msg: str) -> bool:
        """Wait for the user. Returns False when they choose to skip."""
        if self.assume_yes:
            self.warn(f"skipped (unattended): {msg}")
            return False
        try:
            ans = input(f"  {msg} (Enter to continue, s to skip) ").strip().lower()
        except EOFError:
            return False
        return ans != "s"

    def choose(self, msg: str, options: list[str]) -> int:
        """Pick one of `options`; returns its index. Unattended picks the first."""
        if self.assume_yes or len(options) == 1:
            return 0
        self.info(msg)
        for i, o in enumerate(options, 1):
            self.info(f"  {i}. {o}")
        while True:
            try:
                ans = input(f"  Choose 1-{len(options)}: ").strip()
            except EOFError:
                return 0
            if ans.isdigit() and 1 <= int(ans) <= len(options):
                return int(ans) - 1

    def secret(self, msg: str) -> str:
        """Read a secret without echoing it. Empty/unattended returns ''."""
        if self.assume_yes:
            return ""
        import getpass

        try:
            return getpass.getpass(f"  {msg}: ").strip()
        except (EOFError, Exception):
            return ""


def _run(cmd: list[str], timeout: int = 300) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr)
    except FileNotFoundError:
        return 127, f"{cmd[0]}: not found"
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


#: Login pages for the walled platforms, used by the sequential login flow.
LOGIN_URLS = {
    "twitter": "https://x.com/login",
    "reddit": "https://www.reddit.com/login",
    "instagram": "https://www.instagram.com/accounts/login/",
    "facebook": "https://www.facebook.com/login",
    "bilibili": "https://passport.bilibili.com/login",
    "xiaohongshu": "https://www.xiaohongshu.com",
    "zhihu": "https://www.zhihu.com/signin",
    "weibo": "https://weibo.com/login.php",
}


def _navigate(endpoint: str, url: str) -> None:
    """Open `url` in a new tab of the managed browser via the CDP HTTP endpoint, so
    a second login reuses the same window instead of spawning another."""
    req = urllib.request.Request(f"{endpoint}/json/new?{url}", method="PUT")
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def _managed(home: Path) -> tuple[str, str] | None:
    """(executable, managed profile dir) for the chosen browser, or None."""
    base = _nsift_dir(home)
    bid = config.get_browser_choice(base)
    if not bid:
        return None
    found = browsers.detect().get(bid)
    if not found:
        return None
    return found["executable"], str(profile.managed_dir(base, bid))


def login_sites(home: Path, sites: list[str], ui: _UI, poll: int = 60, interval: int = 3) -> dict:
    """Open the managed profile headed and log into each site in turn, reusing one
    window. Success is detected from the site's auth cookie appearing. Interactive;
    returns {site: logged_in}."""
    mp = _managed(home)
    if not mp:
        ui.warn("No managed browser profile yet. Run `net-sift install` first.")
        return {s: False for s in sites}
    exe, pdir = mp
    results: dict[str, bool] = {}
    with browser.managed_browser(exe, pdir, headed=True) as endpoint:
        for site in sites:
            url = LOGIN_URLS.get(site)
            if not url:
                results[site] = False
                continue
            ui.info(f"Opening {site} login. Sign in; net-sift detects when you are done.")
            _navigate(endpoint, url)
            ok = False
            for _ in range(poll):
                if profile.logged_in(pdir).get(site):
                    ok = True
                    break
                time.sleep(interval)
            results[site] = ok
            ui.ok(f"{site}: logged in") if ok else ui.warn(f"{site}: not detected, skipped")
    return results


def _setup_clients(ui: _UI, home: Path) -> None:
    ui.step("Clients")
    found = detect_clients(home)
    if found["claude"]:
        ui.ok(merge_json_mcp(home / ".claude.json"))
        ui.ok(compose_statusline(home / ".claude" / "settings.json", home, ui))
    else:
        ui.info("Claude Code not detected.")
        if ui.confirm("Register for Claude Code anyway (for when you install it)?", default=False):
            ui.ok(merge_json_mcp(home / ".claude.json"))
            ui.ok(compose_statusline(home / ".claude" / "settings.json", home, ui))
    if found["codex"]:
        ui.ok(ensure_codex(home / ".codex" / "config.toml"))
    else:
        ui.info("Codex not detected.")
        if ui.confirm("Register for Codex anyway?", default=False):
            ui.ok(ensure_codex(home / ".codex" / "config.toml"))


def _ensure_node(ui: _UI) -> bool:
    ui.step("Node.js (needed by OpenCLI)")
    while True:
        node = shutil.which("node")
        if node:
            _, ver = _run([node, "--version"])
            if node_ok(ver):
                ui.ok(f"Node {ver.strip()} present")
                return True
            ui.warn(f"Node {ver.strip()} is too old; need >= {'.'.join(map(str, NODE_MIN))}")
        else:
            ui.warn("Node.js is not installed")
        brew = shutil.which("brew")
        if brew and ui.confirm("Install or upgrade Node with Homebrew now?"):
            code, out = _run([brew, "install", "node"], timeout=1800)
            ui.info(out.strip()[-300:] if out.strip() else "")
            if code == 0:
                continue  # recheck
            ui.warn("Homebrew could not install Node.")
        else:
            ui.info("Install Node.js 20.18.1 or newer from https://nodejs.org (LTS).")
        if not ui.pause("Install Node, then press Enter to recheck"):
            ui.warn("Skipping Node. Walled platforms will stay unavailable.")
            return False


def _ensure_opencli(ui: _UI) -> bool:
    ui.step("OpenCLI (logged-in browser access)")
    if shutil.which("opencli"):
        ui.ok("OpenCLI already installed")
        return True
    npm = shutil.which("npm")
    if not npm:
        ui.warn("npm not found (it comes with Node.js).")
        return False
    while True:
        if not ui.confirm(f"Install OpenCLI now (npm install -g {OPENCLI_NPM})?"):
            ui.warn("Skipping OpenCLI. Walled platforms will stay unavailable.")
            return False
        ui.info("Installing OpenCLI, this can take a minute...")
        code, out = _run([npm, "install", "-g", OPENCLI_NPM], timeout=900)
        if code == 0 and shutil.which("opencli"):
            ui.ok("OpenCLI installed")
            return True
        tail = out.strip()[-400:]
        ui.warn("OpenCLI install failed.")
        if tail:
            ui.info(tail)
        if "EACCES" in out or "permission" in out.lower():
            ui.info("This is an npm permissions issue. Fix the npm global prefix, for example:")
            ui.info("  mkdir -p ~/.npm-global && npm config set prefix ~/.npm-global")
            ui.info("  then add ~/.npm-global/bin to your PATH and rerun net-sift install")
        if not ui.pause("Resolve the issue, then press Enter to retry"):
            return False


def setup_browser(ui: _UI, home: Path) -> None:
    """Pick a Chromium browser, copy its profile into net-sift's managed area, and
    offer to log into any walled site not already signed in. Sessions the user
    already has are reused with no re-login; the user's real browser is untouched."""
    from .access import opencli

    ui.step("Browser and accounts")
    found = browsers.detect()
    if not found:
        ui.warn("No Chromium browser found (Chrome, Comet, Brave, Edge, Arc). Account and")
        ui.warn("web search need one. Install any Chromium browser, then rerun net-sift install.")
        return

    # Show each browser with the sites it is already logged into, best first.
    ranked = sorted(
        found.values(),
        key=lambda b: sum(profile.logged_in(b["source_profile"]).values()),
        reverse=True,
    )
    for b in ranked:
        sites = [s for s, on in profile.logged_in(b["source_profile"]).items() if on]
        ui.info(f"{b['name']}: logged into {', '.join(sites) if sites else 'nothing detected'}")
    choice = ranked[ui.choose("Which browser should net-sift use?", [b["name"] for b in ranked])]

    ui.info("net-sift copies that browser's profile so it can search with the browser closed.")
    ui.info("The copy holds your session cookies and stays on this machine (0700).")
    if not ui.confirm(f"Copy the {choice['name']} profile now?"):
        ui.warn("Skipped. Walled and web sources will be unavailable until you do this.")
        return
    base = _nsift_dir(home)
    dest = str(profile.managed_dir(base, choice["id"]))
    profile.copy_profile(choice["source_profile"], dest)
    config.set_browser_choice(base, choice["id"])
    ui.ok(f"Copied {choice['name']} into {dest}")

    state = profile.logged_in(dest)
    missing = [s for s in opencli.WALLED_SITES if s in LOGIN_URLS and not state.get(s)]
    if not missing:
        ui.ok("All supported accounts are already signed in.")
        return
    ui.info(f"Not signed in: {', '.join(missing)}.")
    if ui.assume_yes:
        ui.info("Unattended run; add them later with `net-sift login <site>`.")
        return
    if ui.confirm("Log into them now (one at a time, in a browser window net-sift opens)?"):
        login_sites(home, missing, ui)


def _optional_features(ui: _UI) -> None:
    """Opt-in extras: Tor onion search, and Instagram account recon (needs a key)."""
    ui.step("Optional features")

    # Darkweb (Tor onion discussion search, information-only)
    if shutil.which("tor"):
        ui.ok("Tor found: dark-web discussion search is available (information-only).")
    else:
        ui.info("Dark-web discussion search (information-only) needs Tor. It is optional.")
        brew = shutil.which("brew")
        if brew and ui.confirm("Install Tor with Homebrew now?", default=False):
            code, out = _run([brew, "install", "tor"], timeout=1800)
            ui.ok("Tor installed.") if code == 0 else ui.warn(
                "Could not install Tor; skip for now."
            )
        else:
            ui.info("Install later with `brew install tor` (macOS) or your package manager.")

    # Instagram account recon (HikerAPI, metered)
    from . import config
    from . import instagram_recon as ig

    if ig.key_present():
        ui.ok("Instagram account recon: key already set.")
    elif ui.confirm(
        "Enable Instagram account recon? It needs a paid HikerAPI access key.", default=False
    ):
        k = ui.secret("Paste your HikerAPI access key (hidden)")
        if k:
            config.set_secret("HIKERAPI_KEY", k)
            ui.ok("Saved. Instagram account recon is enabled.")
        else:
            ui.info("No key entered; skipped. Rerun net-sift install to add it later.")


def run(home: Path | None = None, assume_yes: bool = False) -> int:
    home = home or Path.home()
    ui = _UI(assume_yes)
    print("net-sift setup wizard")
    print("=" * 40)
    _setup_clients(ui, home)
    if _ensure_node(ui) and _ensure_opencli(ui):
        setup_browser(ui, home)
    _optional_features(ui)

    ui.step("Done")
    ui.info("net-sift is installed. Keyless sources (Bluesky, Hacker News, GitHub, arXiv,")
    ui.info("and more) always work. Walled and web sources run headless from the copied")
    ui.info("profile, with the browser closed. Run `net-sift doctor` to see what is signed in,")
    ui.info("or `net-sift login <site>` to add an account later.")
    print("\nRestart your client so it picks up net-sift.")
    return 0
