"""Lightweight JSON-backed chat session history."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings


class SessionStore:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or settings.workspace_dir / "sessions"

    def _path(self, thread_id: str) -> Path:
        safe = "".join(ch for ch in thread_id if ch.isalnum() or ch in ("-", "_"))[:64]
        return self.root / f"{safe}.json"

    def _load(self, thread_id: str) -> dict[str, Any]:
        path = self._path(thread_id)
        if not path.exists():
            return {"thread_id": thread_id, "messages": []}
        return json.loads(path.read_text(encoding="utf-8"))

    def _save(self, thread_id: str, data: dict[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        path = self._path(thread_id)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def record_turn(
        self,
        *,
        thread_id: str,
        agent_id: str,
        user_message: str,
        assistant_message: str,
        trace_id: str = "",
        run_id: str = "",
        source: str = "user",
        attachment_refs: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        data = self._load(thread_id)
        data.update(
            {
                "thread_id": thread_id,
                "agent_id": agent_id or data.get("agent_id", "default"),
                "updated_at": now,
                "created_at": data.get("created_at", now),
                "last_trace_id": trace_id or data.get("last_trace_id", ""),
                "last_run_id": run_id or data.get("last_run_id", ""),
                "source": source,
            }
        )
        data.setdefault("messages", [])
        user_entry: dict[str, Any] = {"role": "user", "content": user_message, "created_at": now}
        if attachment_refs:
            user_entry["attachment_refs"] = attachment_refs
        data["messages"].append(user_entry)
        data["messages"].append(
            {
                "role": "assistant",
                "content": assistant_message,
                "created_at": now,
                "trace_id": trace_id,
                "run_id": run_id,
            }
        )
        self._save(thread_id, data)
        return data

    def list_sessions(
        self,
        query: str = "",
        limit: int = 50,
        *,
        include_archived: bool = False,
        archived_only: bool = False,
    ) -> list[dict[str, Any]]:
        self.root.mkdir(parents=True, exist_ok=True)
        rows: list[dict[str, Any]] = []
        q = query.lower().strip()
        for path in self.root.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            archived = bool(data.get("archived"))
            if archived_only and not archived:
                continue
            if not include_archived and not archived_only and archived:
                continue
            messages = data.get("messages", [])
            title = next((m.get("content", "") for m in messages if m.get("role") == "user"), data["thread_id"])
            haystack = " ".join([data.get("thread_id", ""), title, *(m.get("content", "") for m in messages)]).lower()
            if q and q not in haystack:
                continue
            rows.append(
                {
                    "thread_id": data.get("thread_id", path.stem),
                    "agent_id": data.get("agent_id", "default"),
                    "title": title[:80],
                    "message_count": len(messages),
                    "updated_at": data.get("updated_at", data.get("created_at", "")),
                    "last_trace_id": data.get("last_trace_id", ""),
                    "last_run_id": data.get("last_run_id", ""),
                    "archived": archived,
                    "archived_at": data.get("archived_at", ""),
                }
            )
        rows.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
        return rows[:limit]

    def get_session(self, thread_id: str) -> dict[str, Any] | None:
        path = self._path(thread_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def archive_session(self, thread_id: str) -> dict[str, Any] | None:
        data = self.get_session(thread_id)
        if data is None:
            return None
        now = datetime.now(timezone.utc).isoformat()
        data["archived"] = True
        data["archived_at"] = data.get("archived_at") or now
        data["updated_at"] = now
        self._save(thread_id, data)
        return data

    def unarchive_session(self, thread_id: str) -> dict[str, Any] | None:
        data = self.get_session(thread_id)
        if data is None:
            return None
        now = datetime.now(timezone.utc).isoformat()
        data["archived"] = False
        data["archived_at"] = ""
        data["updated_at"] = now
        self._save(thread_id, data)
        return data

    def delete_session(self, thread_id: str) -> bool:
        path = self._path(thread_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def export_markdown(self, thread_id: str) -> str | None:
        data = self.get_session(thread_id)
        if data is None:
            return None
        lines = [f"# BoetClaw Session {thread_id}", ""]
        for msg in data.get("messages", []):
            role = "用户" if msg.get("role") == "user" else "助手"
            lines.append(f"## {role}")
            lines.append("")
            lines.append(str(msg.get("content", "")))
            lines.append("")
        return "\n".join(lines)


session_store = SessionStore()
