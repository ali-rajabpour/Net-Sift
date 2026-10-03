# Contributing

Thanks for your interest in Net-Sift.

## Contribution policy (CLA + sign-off)

By opening a pull request you agree to the [Contributor License Agreement](CLA.md):
you keep your copyright and authorship, and you grant the maintainer a license to
use and relicense your contribution so the project's licensing stays coherent.

Every commit must be signed off, which certifies the Developer Certificate of
Origin. Use `git commit -s` to add the line:

```
Signed-off-by: Your Name <your@email>
```

CI checks that commits in a pull request are signed off.

## Development setup

```bash
git clone https://github.com/ali-rajabpour/Net-Sift.git
cd Net-Sift
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Before you open a pull request

```bash
ruff check net_sift tests     # lint
ruff format net_sift tests    # format
pytest                        # tests
```

- Keep the engine dependency-light. New third-party dependencies need a clear
  reason.
- Add a test for any non-trivial logic. Tests must not hit the network; use
  fixtures and temp paths.
- Each source is a callable `(query, since, until, budget) -> (records, ceiling)`.
  Follow that contract and emit the record shape from `net_sift.engine.core.rec`.
- Update `CHANGELOG.md` under "Unreleased".

## Scope

Net-Sift fetches and ranks public content for research. It does not post, comment,
or perform any write action on any platform, and it does not bypass authentication.
Keep contributions within that scope.

## Adding a source

- Keyless source: add it to `net_sift/engine/sources.py` and register it in
  `SOURCES`.
- Walled platform: it is reached through OpenCLI. If OpenCLI gains an adapter,
  add the site to `WALLED_SITES` in `net_sift/access/opencli.py`.
