# Release Notes

## v0.1.0 — First public release (2026-07-20)

**Positioning:** single-node MVP with a first React management console. Not production-ready; not multi-instance HA.

### Included

- FastAPI backend with DeepAgents / LangGraph agent runtime, ToolGuard, Plan Gate, skills, plugins, MCP hooks
- Multi-agent workspaces with per-agent SQLite checkpoints (single machine)
- Domain CRUD (wells, sections, daily reports, parameters, LAS upload)
- Gateway stubs for DingTalk, Feishu, QQ, Telegram with configurable webhook verification
- Cron / Heartbeat scheduling with JSON persistence
- React console: chat, plan confirm, approvals, tasks, agents, traces, settings
- Vitest component/protocol tests, Playwright E2E (fake Provider), GitHub Actions CI workflow
- Docker Compose, install scripts, OpenAPI snapshot gate

### Known limitations

- No RBAC; optional API token / console password only
- No cross-process or post-restart cancellation of active runs
- No multi-replica consistency for checkpoints, approvals, or JSON stores
- Real LLM Provider and channel delivery are manual / optional, not default CI gates
- ToolGuard is application-layer policy, not an OS sandbox

### Verify locally

```powershell
.\scripts\ci-local.ps1
```

See [`TESTING.md`](TESTING.md) and [`PROJECT_STATUS_REPORT.md`](PROJECT_STATUS_REPORT.md) for the 2026-07-20 validation baseline.
