#!/usr/bin/env python
"""Optional E2E helper: start API with isolated workspace + fake Agent graphs.

Default Playwright PR-gate suite does **not** require this process; it uses
route-level fake Provider responses in ``frontend/e2e/fixtures/fakeBackend.ts``.

Use this script when you want a real ASGI stack with stubbed Agent resolution
(no external LLM) and a disposable workspace directory:

  cd backend
  .\\.venv\\Scripts\\python.exe scripts\\e2e_fake_server.py

Env:
  E2E_WORKSPACE_DIR  Isolated workspace root (default: system temp / boetclaw-e2e-*)
  E2E_PORT           Listen port (default: 18000)
  CONSOLE_PASSWORD   Optional console gate password
  API_TOKEN          Optional API token
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class FakeAgent:
    """Minimal async Agent compatible with chat orchestration streaming."""

    def __init__(self, *, interrupt_type: str = "") -> None:
        self.interrupt_type = interrupt_type

    async def ainvoke(self, state: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        from langchain_core.messages import AIMessage

        return {"messages": [AIMessage(content="fake-sync-ok")], "todos": []}

    async def astream(self, state: dict[str, Any], config: dict[str, Any], **_: Any):
        from langchain_core.messages import AIMessageChunk

        yield ("", "messages", (AIMessageChunk(content="fake-stream-ok"), {}))
        if self.interrupt_type:
            payload: dict[str, Any] = {"type": self.interrupt_type}
            if self.interrupt_type == "tool_approval":
                payload["approval_id"] = "approval-e2e"
            yield ("", "updates", {"planner": {"todos": ["e2e-step"]}})
            yield (
                "",
                "updates",
                {"__interrupt__": [{"id": "interrupt-e2e", "value": payload}]},
            )


def _prepare_workspace() -> Path:
    raw = os.environ.get("E2E_WORKSPACE_DIR")
    root = Path(raw) if raw else Path(tempfile.mkdtemp(prefix="boetclaw-e2e-"))
    root.mkdir(parents=True, exist_ok=True)
    os.environ["WORKSPACE_DIR"] = str(root)
    os.environ.setdefault("CHECKPOINT_BACKEND", "memory")
    os.environ.setdefault("CHECKPOINT_SQLITE_PATH", str(root / "checkpoints"))
    print(f"[e2e_fake_server] WORKSPACE_DIR={root}")
    return root


def _install_fakes() -> None:
    from app.services import chat_orchestration
    from app.services.execution_resume import graph_resume_adapter

    agents = {
        "default": FakeAgent(),
        "workspace-a": FakeAgent(),
        "planner": FakeAgent(interrupt_type="plan_confirm"),
    }

    async def resolve(agent_id: str):
        if agent_id not in agents:
            error = ValueError(f"unknown agent: {agent_id}")
            error.status_code = 404  # type: ignore[attr-defined]
            raise error
        return agents[agent_id]

    chat_orchestration.resolve_agent_graph = resolve  # type: ignore[method-assign]
    graph_resume_adapter.register = lambda *_args, **_kwargs: None  # type: ignore[method-assign]


def main() -> None:
    _prepare_workspace()
    port = int(os.environ.get("E2E_PORT", "18000"))

    import uvicorn

    from app.main import app

    _install_fakes()
    print(f"[e2e_fake_server] listening on http://127.0.0.1:{port}")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    main()
