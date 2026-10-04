"""Net-Sift: coverage-first social and web deep-search as an MCP server."""

from importlib.metadata import PackageNotFoundError, version

try:
    # Single source of truth: the version declared in pyproject.toml / wheel metadata.
    __version__ = version("net-sift")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0.0.0+dev"
