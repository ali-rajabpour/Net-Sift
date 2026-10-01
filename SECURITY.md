# Security Policy

## Reporting a vulnerability

Please report security issues privately through GitHub's private vulnerability
reporting (the "Report a vulnerability" button under the repository's Security tab)
rather than opening a public issue. You will get an acknowledgement, and a fix or
mitigation will be coordinated before any public disclosure.

## Scope and design notes

- Net-Sift does not store credentials. Optional API keys are read from environment
  variables at runtime only, never written to disk by this project.
- Walled platforms are reached through the user's own logged-in browser via
  OpenCLI. Net-Sift does not read, copy, or exfiltrate browser cookies.
- Search results are written to `~/.net-sift/sessions/` on the local machine only
  and are deleted on explicit user confirmation.
- Remote XML feeds are parsed with `defusedxml` to guard against entity-expansion
  and external-entity attacks.

## Supported versions

The latest released version receives security fixes.
