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
import platform
import shutil
import subprocess
from pathlib import Path

MCP_ENTRY = {"command": "net-sift", "args": ["serve"]}
NODE_MIN = (20, 18, 1)
OPENCLI_NPM = "@jackwener/opencli"
OPENCLI_EXTENSION_URL = (
    "https://chromewebstore.google.com/detail/opencli/ildkmabpimmkaediidaifkhjpohdnifk"
)


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
    if data.get("statusLine") == line:
        return f"status bar already set in {path}"
    data["statusLine"] = line
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return f"status bar set in {path}"


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


def _run(cmd: list[str], timeout: int = 300) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr)
    except FileNotFoundError:
        return 127, f"{cmd[0]}: not found"
    except (OSError, subprocess.SubprocessError) as e:
        return 1, str(e)


def _open_url(url: str) -> None:
    opener = {"Darwin": ["open"], "Windows": ["cmd", "/c", "start", ""]}.get(
        platform.system(), ["xdg-open"]
    )
    try:
        subprocess.Popen(opener + [url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _setup_clients(ui: _UI, home: Path) -> None:
    ui.step("Clients")
    found = detect_clients(home)
    if found["claude"]:
        ui.ok(merge_json_mcp(home / ".claude.json"))
        ui.ok(ensure_statusline(home / ".claude" / "settings.json"))
    else:
        ui.info("Claude Code not detected.")
        if ui.confirm("Register for Claude Code anyway (for when you install it)?", default=False):
            ui.ok(merge_json_mcp(home / ".claude.json"))
            ui.ok(ensure_statusline(home / ".claude" / "settings.json"))
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


def _connect_bridge(ui: _UI) -> bool:
    """Make sure OpenCLI's browser bridge is connected (daemon + extension)."""
    from .access import opencli

    ui.step("Connect your browser")
    ui.info("Starting OpenCLI and checking your browser...")
    if opencli.available():  # runs `opencli doctor`, which starts the daemon
        ui.ok("Browser connected")
        return True
    ui.info("net-sift reads sites you are logged into (X, Reddit, Instagram, and more)")
    ui.info("through a Chromium browser (Chrome, Edge, Brave, Arc, Comet).")
    ui.info("One-time step: install the OpenCLI Browser Bridge extension, either one:")
    ui.info(f"   - Chrome Web Store: {OPENCLI_EXTENSION_URL}")
    ui.info("   - or the opencli-extension zip from")
    ui.info("     https://github.com/jackwener/opencli/releases (unzip, open chrome://extensions,")
    ui.info("     turn on Developer mode, click Load unpacked).")
    if ui.confirm("Open the Chrome Web Store page now?"):
        _open_url(OPENCLI_EXTENSION_URL)
    while True:
        if not ui.pause("Press Enter once the extension is installed and your browser is open"):
            ui.warn("Skipping account setup. Rerun net-sift install any time.")
            return False
        ui.info("Checking (takes a few seconds)...")
        if opencli.available():
            ui.ok("Browser connected")
            return True
        ui.warn("Still not connected. Keep the browser open with the extension enabled.")


def _connect_accounts(ui: _UI) -> None:
    """Check each social account one by one; offer to connect the ones that are not."""
    from .access import opencli

    ui.step("Your accounts")
    ui.info("Checking each site you can search. This opens your browser briefly per site.")
    for site in opencli.WALLED_SITES:
        name, url = opencli.WALLED_META[site]
        ui.info(f"Checking {name}...")
        if opencli.probe_login(site):
            ui.ok(f"{name}: connected")
            continue
        if not ui.confirm(f"{name} is not connected. Connect it now?", default=True):
            ui.info(f"{name}: skipped")
            continue
        ui.info(f"Log into {name}: opening {url}")
        ui.info("Sign in as normal in that browser, then come back here.")
        _open_url(url)
        while True:
            if not ui.pause(f"Press Enter once you are logged into {name}"):
                ui.info(f"{name}: skipped")
                break
            ui.info("Verifying...")
            if opencli.probe_login(site):
                ui.ok(f"{name}: connected")
                break
            if not ui.confirm(f"{name} still not working. Try again?", default=False):
                ui.info(f"{name}: skipped")
                break


def run(home: Path | None = None, assume_yes: bool = False) -> int:
    home = home or Path.home()
    ui = _UI(assume_yes)
    print("net-sift setup wizard")
    print("=" * 40)
    _setup_clients(ui, home)
    if _ensure_node(ui) and _ensure_opencli(ui) and _connect_bridge(ui):
        _connect_accounts(ui)

    ui.step("Done")
    ui.info("net-sift is installed. Keyless sources (Bluesky, Hacker News, GitHub, arXiv,")
    ui.info("and more) always work. The accounts you connected above are searchable too.")
    ui.info("Run `net-sift doctor` any time to see what is connected.")
    print("\nRestart your client so it picks up net-sift.")
    return 0
