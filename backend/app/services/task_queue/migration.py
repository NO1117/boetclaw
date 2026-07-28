"""Migrate legacy task_history.json into SQLite."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from app.services.task_queue.models import TaskStatus, utc_now_iso
from app.services.task_queue.sanitizer import sanitize_metadata, sanitize_text


def _legacy_status(value: str) -> str:
    if value in {"pending", "running", "cancelling", "completed", "failed", "cancelled"}:
        if value == "pending":
            return TaskStatus.QUEUED.value
        if value in {"running", "cancelling"}:
            return TaskStatus.INTERRUPTED.value
        return value
    return TaskStatus.QUEUED.value


def migrate_json_history(conn: sqlite3.Connection, json_path: Path) -> int:
    if not json_path.exists():
        return 0
    try:
        rows = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return 0
    if not isinstance(rows, list):
        return 0

    migrated = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        task_id = str(row.get("id") or "").strip()
        if not task_id:
            continue
        exists = conn.execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if exists:
            continue
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        agent_id = str(metadata.get("agent_id") or "default")
        status = _legacy_status(str(row.get("status") or "pending"))
        error = sanitize_text(str(row.get("error") or ""), max_chars=4000)
        if status == TaskStatus.INTERRUPTED.value and not error:
            error = "Task interrupted by service restart"
        result = sanitize_text(str(row.get("result") or ""), max_chars=8000)
        prompt = sanitize_text(str(row.get("prompt") or ""), max_chars=8000)
        title = sanitize_text(str(row.get("title") or ""), max_chars=512)
        now = utc_now_iso()
        conn.execute(
            """
            INSERT INTO tasks (
                id, title, prompt, status, agent_id, thread_id, trace_id, run_id,
                result, error, gateway, gateway_user, metadata_json, source,
                created_at, updated_at, migrated_from_json, revision
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1)
            """,
            (
                task_id,
                title,
                prompt,
                status,
                agent_id,
                str(row.get("thread_id") or ""),
                str(row.get("trace_id") or ""),
                str(row.get("run_id") or ""),
                result,
                error,
                str(row.get("gateway") or ""),
                str(row.get("gateway_user") or ""),
                json.dumps(sanitize_metadata(metadata), ensure_ascii=False),
                "legacy_json",
                str(row.get("created_at") or now),
                str(row.get("updated_at") or now),
            ),
        )
        conn.execute(
            """
            INSERT INTO task_events (task_id, event_type, payload_json, created_at)
            VALUES (?, 'migrated', ?, ?)
            """,
            (
                task_id,
                json.dumps({"source": "task_history.json"}, ensure_ascii=False),
                now,
            ),
        )
        migrated += 1
    if migrated:
        conn.commit()
    return migrated
