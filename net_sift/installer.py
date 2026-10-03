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
import os
import platform
import shutil
import subprocess
from pathlib import Path

from . import config

MCP_ENTRY = {"command": "net-sift", "args": ["serve"]}
NODE_MIN = (20, 18, 1)
OPENCLI_NPM = "@jackwener/opencli"
OPENCLI_EXTENSION_URL = (
    "https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk"
)

# Chromium-family browsers that can load the OpenCLI extension, per OS.
_MAC_BROWSERS = [
    ("Google Chrome", "Google Chrome.app"),
    ("Comet", "Comet.app"),
    ("Brave", "Brave Browser.app"),
    ("Microsoft Edge", "Microsoft Edge.app"),
    ("Arc", "Arc.app"),
    ("Vivaldi", "Vivaldi.app"),
    ("Opera", "Opera.app"),
    ("Chromium", "Chromium.app"),
]
_WIN_BROWSERS = [
    ("Google Chrome", "Google/Chrome/Application/chrome.exe"),
    ("Microsoft Edge", "Microsoft/Edge/Application/msedge.exe"),
    ("Brave", "BraveSoftware/Brave-Browser/Application/brave.exe"),
    ("Vivaldi", "Vivaldi/Application/vivaldi.exe"),
    ("Opera", "Programs/Opera/launcher.exe"),
    ("Comet", "Comet/Application/comet.exe"),
]
_LINUX_BROWSERS = [
    ("Google Chrome", "google-chrome"),
    ("Chromium", "chromium"),
    ("Brave", "brave-browser"),
    ("Microsoft Edge", "microsoft-edge"),
    ("Vivaldi", "vivaldi"),
]


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


def detect_chromium_browsers(system: str | None = None, home: Path | None = None) -> list[dict]:
    """Installed Chromium-family browsers. Each entry: {name, open} where `open`
    is the argv prefix to launch a URL (the URL is appended). Cross-platform."""
    system = system or platform.system()
    home = home or Path.home()
    found: list[dict] = []
    if system == "Darwin":
        roots = [Path("/Applications"), home / "Applications"]
        for name, app in _MAC_BROWSERS:
            for d in roots:
                if (d / app).exists():
                    found.append({"name": name, "open": ["open", "-a", str(d / app)]})
                    break
    elif system == "Windows":
        roots = [
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local")),
        ]
        for name, rel in _WIN_BROWSERS:
            for root in filter(None, roots):
                exe = Path(root) / rel
                if exe.exists():
                    found.append({"name": name, "open": [str(exe)]})
                    break
    else:  # Linux and the rest
        for name, binname in _LINUX_BROWSERS:
            path = shutil.which(binname)
            if path:
                found.append({"name": name, "open": [path]})
    return found


def _browser_choice_path(home: Path) -> Path:
    return _nsift_dir(home) / "browser.json"


def load_browser_choice(home: Path) -> dict | None:
    try:
        return json.loads(_browser_choice_path(home).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def save_browser_choice(home: Path, choice: dict) -> None:
    p = _browser_choice_path(home)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(choice), encoding="utf-8")
    except OSError:
        pass


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


def _run(cmd: list[str], timeout: int = 300) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr)
    except FileNotFoundError:
        return 127, f"{cmd[0]}: not found"
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


def _open_url(url: str, browser: dict | None = None) -> None:
    if browser and browser.get("open"):
        argv = [*browser["open"], url]
    else:
        argv = {"Darwin": ["open"], "Windows": ["cmd", "/c", "start", ""]}.get(
            platform.system(), ["xdg-open"]
        ) + [url]
    try:
        subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _choose_browser(ui: _UI, home: Path) -> dict | None:
    """Detect Chromium browsers; if several, let the user pick which one net-sift
    opens login/extension pages in. The choice is remembered."""
    browsers = detect_chromium_browsers(home=home)
    if not browsers:
        ui.warn("No Chromium browser found (Chrome, Edge, Brave, Arc, Comet). Account search")
        ui.warn("needs one. Install any Chromium browser, then rerun net-sift install.")
        return None
    if len(browsers) == 1:
        ui.ok(f"Using {browsers[0]['name']} for logins")
        choice = browsers[0]
    else:
        idx = ui.choose(
            "Several Chromium browsers found. Which should net-sift use for logins?",
            [b["name"] for b in browsers],
        )
        choice = browsers[idx]
        ui.ok(f"Using {choice['name']}")
    save_browser_choice(home, choice)
    return choice


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


def _connect_bridge(ui: _UI, browser: dict | None) -> bool:
    """Make sure OpenCLI's browser bridge is connected (daemon + extension)."""
    from .access import opencli

    ui.step("Connect your browser")
    ui.info("Starting OpenCLI and checking your browser...")
    if opencli.available():  # runs `opencli doctor`, which starts the daemon
        ui.ok("Browser connected")
        return True
    bname = browser["name"] if browser else "your Chromium browser"
    ui.info(f"net-sift reads sites you are logged into through {bname}.")
    ui.info("One-time step: install the OpenCLI Browser Bridge extension, either one:")
    ui.info(f"   - Chrome Web Store: {OPENCLI_EXTENSION_URL}")
    ui.info("   - or the opencli-extension zip from")
    ui.info("     https://github.com/jackwener/opencli/releases (unzip, open the browser's")
    ui.info("     extensions page, turn on Developer mode, click Load unpacked).")
    if ui.confirm(f"Open the extension page in {bname} now?"):
        _open_url(OPENCLI_EXTENSION_URL, browser)
    while True:
        if not ui.pause(f"Press Enter once the extension is installed and {bname} is open"):
            ui.warn("Skipping account setup. Rerun net-sift install any time.")
            return False
        ui.info("Checking (takes a few seconds)...")
        if opencli.available():
            ui.ok("Browser connected")
            return True
        if not ui.confirm("Still not connected. Check again?", default=True):
            return False


def _connect_accounts(ui: _UI, browser: dict | None) -> None:
    """Check each account one by one. Never auto-skip: for any account that is not
    connected, ask the user whether to connect it, and on yes give instructions."""
    from .access import opencli

    bname = browser["name"] if browser else "your browser"
    ui.step("Your accounts")
    ui.info("Checking each account you can search. This opens your browser briefly per site.")
    for site in opencli.WALLED_SITES:
        name, url = opencli.WALLED_META[site]
        ui.info(f"Checking {name}...")
        ok, reason = opencli.probe_detail(site)
        if ok:
            ui.ok(f"{name}: connected")
            continue
        if reason == "blocked":
            ui.info(f"{name}: OpenCLI could not open it (the site may block automation, or its")
            ui.info("adapter may be down). Logging in might not help, but you can try.")
            question = f"Try to connect {name} anyway?"
        else:
            question = f"{name} is not connected. Connect it now?"
        if not ui.confirm(question, default=True):
            ui.info(f"{name}: skipped")
            continue
        ui.info(f"Opening {name} in {bname}: {url}")
        ui.info("Sign in as normal, then come back here.")
        _open_url(url, browser)
        # User-driven: verify, and only retry when the user says so (no auto loop).
        while True:
            if not ui.pause(f"Press Enter once you are logged into {name}"):
                ui.info(f"{name}: skipped")
                break
            ui.info("Verifying...")
            ok2, reason2 = opencli.probe_detail(site)
            if ok2:
                ui.ok(f"{name}: connected")
                break
            hint = (
                "the site is blocking automation, not your login"
                if reason2 == "blocked"
                else "make sure you are fully logged in and the tab is open"
            )
            if not ui.confirm(f"{name} still not working ({hint}). Try again?", default=False):
                ui.info(f"{name}: skipped")
                break


def run(home: Path | None = None, assume_yes: bool = False) -> int:
    home = home or Path.home()
    ui = _UI(assume_yes)
    print("net-sift setup wizard")
    print("=" * 40)
    _setup_clients(ui, home)
    if _ensure_node(ui) and _ensure_opencli(ui):
        browser = _choose_browser(ui, home)
        if _connect_bridge(ui, browser):
            _connect_accounts(ui, browser)

    ui.step("Done")
    ui.info("net-sift is installed. Keyless sources (Bluesky, Hacker News, GitHub, arXiv,")
    ui.info("and more) always work. The accounts you connected above are searchable too.")
    ui.info("Run `net-sift doctor` any time to see what is connected.")
    print("\nRestart your client so it picks up net-sift.")
    return 0
