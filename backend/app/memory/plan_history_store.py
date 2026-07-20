"""JSON-backed plan confirmation audit history."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.core.execution_ref import ExecutionRef


class PlanHistoryStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (settings.workspace_dir / "plans" / "plan_history.json")

    def _load(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        try:
            rows = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        return rows if isinstance(rows, list) else []

    def _save(self, rows: list[dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    def record(
        self,
        *,
        thread_id: str = "",
        execution_ref: ExecutionRef | None = None,
        action: str,
        todos: list[Any] | None = None,
        edited_todos: list[Any] | None = None,
        response: str = "",
    ) -> dict[str, Any]:
        row = {
            "id": uuid.uuid4().hex[:12],
            "agent_id": execution_ref.agent_id if execution_ref else "default",
            "thread_id": execution_ref.thread_id if execution_ref else thread_id,
            "interrupt_id": execution_ref.interrupt_id if execution_ref else "",
            "execution_ref": execution_ref.model_dump() if execution_ref else None,
            "action": action,
            "todos": todos or [],
            "edited_todos": edited_todos or [],
            "response": response,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        rows = self._load()
        rows.append(row)
        self._save(rows)
        return row

    @staticmethod
    def _agent_id(row: dict[str, Any]) -> str:
        if isinstance(row.get("agent_id"), str) and row["agent_id"]:
            return row["agent_id"]
        execution_ref = row.get("execution_ref")
        if isinstance(execution_ref, dict) and isinstance(execution_ref.get("agent_id"), str):
            return execution_ref["agent_id"]
        return "default"

    def has_pending(self, execution_ref: ExecutionRef) -> bool:
        """Check that the exact server-issued plan reference is still pending."""
        matching = [
            row
            for row in self._load()
            if row.get("execution_ref") == execution_ref.model_dump()
        ]
        if not matching:
            return False
        matching.sort(key=lambda row: row.get("created_at", ""))
        return matching[-1].get("action") == "created"

    def list(
        self,
        thread_id: str = "",
        limit: int = 100,
        agent_id: str = "",
    ) -> list[dict[str, Any]]:
        rows = self._load()
        if agent_id:
            rows = [row for row in rows if self._agent_id(row) == agent_id]
        if thread_id:
            rows = [row for row in rows if row.get("thread_id") == thread_id]
        rows.sort(key=lambda row: row.get("created_at", ""), reverse=True)
        return rows[:limit]


plan_history_store = PlanHistoryStore()
