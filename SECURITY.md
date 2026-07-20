# Security Policy

BoetClaw is a **local-first single-node MVP**. It is not production-hardened by default. See [`docs/SECURITY.md`](docs/SECURITY.md) for implemented controls, configuration guidance, and known limitations.

## Supported versions

| Version | Supported |
| --- | --- |
| `0.1.x` (main) | Best-effort fixes for confirmed vulnerabilities affecting the default local/single-node deployment |

## Reporting a vulnerability

Please **do not** open a public GitHub issue for security-sensitive reports.

1. Use [GitHub Security Advisories](https://github.com/NO1117/boetclaw/security/advisories/new) for this repository when available, **or**
2. Open a private report via repository maintainer contact on the GitHub profile.

Include: affected component/path, reproduction steps, impact assessment, and suggested fix if known. We aim to acknowledge reports within 7 days.

## Scope notes

Out of scope for this MVP unless explicitly documented otherwise:

- Misconfiguration on internet-exposed deployments (empty `API_TOKEN`, disabled webhook secrets, permissive CORS)
- Third-party LLM provider or messaging platform credentials stored in local `.env`
- Supply-chain issues in upstream dependencies (track via project CI audits)

Do not commit real API keys, webhook secrets, or production workspace data to the repository.
