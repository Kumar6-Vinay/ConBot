# Security Policy

ConBOT is a small, actively-maintained MVP. If you find a security issue,
please report it privately rather than opening a public GitHub issue —
this repo is public, and a public issue discloses the problem before
there's a chance to fix it.

## Reporting a vulnerability

Use GitHub's [private vulnerability reporting](https://github.com/Kumar6-Vinay/ConBot/security/advisories/new)
for this repository (Security tab → Report a vulnerability). This opens a
private advisory visible only to the maintainer until a fix is ready.

If that's not available to you, open an issue asking for a contact method
without describing the vulnerability itself.

## What's in scope

- The FastAPI backend (`app/`)
- The static frontend (`frontend/`)
- Build/deploy configuration (`Dockerfile`, `wrangler.json`, CI config)

## What's out of scope

- Findings that require physical access to the maintainer's machine or
  accounts
- Reports against third-party services ConBOT calls (Google Gemini,
  OpenRouter, Pollinations.ai) — report those to the provider directly
- Denial-of-service via raw traffic volume against the free-tier hosting
  (Render/Cloudflare) rather than an application-level bug

## Response

This is a solo-maintained MVP, not a funded security team — expect an
initial response within a few days, not a formal SLA. Known findings and
their fix status are tracked in [`SECURITY_AUDIT.md`](./SECURITY_AUDIT.md).
