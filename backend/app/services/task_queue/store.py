"""SQLite WAL persistence for durable task queue."""

from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.task_queue.migration import migrate_json_history
from app.services.task_queue.models import BackoffStrategy, TaskAttempt, TaskEvent, TaskRecord, TaskStatus, utc_now_iso
from app.services.task_queue.sanitizer import sanitize_metadata, sanitize_snapshot, sanitize_text

SCHEMA_VERSION = 1


def _row_to_task(row: sqlite3.Row) -> TaskRecord:
    return TaskRecord(
        id=row["id"],
        title=row["title"],
        prompt=row["prompt"],
        status=TaskStatus(row["status"]),
        agent_id=row["agent_id"],
        priority=row["priority"],
        scheduled_at=row["scheduled_at"] or "",
        max_attempts=row["max_attempts"],
        attempt_count=row["attempt_count"],
        backoff_strategy=BackoffStrategy(row["backoff_strategy"]),
        backoff_base_seconds=row["backoff_base_seconds"],
        backoff_max_seconds=row["backoff_max_seconds"],
        timeout_seconds=row["timeout_seconds"],
        idempotency_key=row["idempotency_key"] or "",
        thread_id=row["thread_id"] or "",
        trace_id=row["trace_id"] or "",
        run_id=row["run_id"] or "",
        result=row["result"] or "",
        error=row["error"] or "",
        gateway=row["gateway"] or "",
        gateway_user=row["gateway_user"] or "",
        source=row["source"] or "api",
        revision=row["revision"],
        retry_after=row["retry_after"] or "",
        run_snapshot_json=row["run_snapshot_json"] or "{}",
        metadata_json=row["metadata_json"] or "{}",
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        lease_owner=row["lease_owner"] or "",
        lease_expires_at=row["lease_expires_at"] or "",
        migrated_from_json=row["migrated_from_json"],
    )


class TaskQueueStore:
    def __init__(
        self,
        db_path: Path | None = None,
        legacy_json_path: Path | None = None,
    ) -> None:
        self.db_path = db_path or settings.task_queue_sqlite_path
        self.legacy_json_path = legacy_json_path or settings.task_queue_legacy_json_path
        self._enforce_workspace_path = db_path is None
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None

    def initialize(self) -> None:
        with self._lock:
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            resolved = self.db_path.resolve()
            if ".." in self.db_path.parts:
                raise ValueError("task queue sqlite path must not contain parent traversal")
            if self._enforce_workspace_path:
                workspace_root = settings.workspace_dir.resolve()
                if workspace_root not in resolved.parents and resolved != workspace_root:
                    raise ValueError("task queue sqlite path must stay under workspace_dir")
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._migrate_schema()
            migrate_json_history(self._conn, self.legacy_json_path)
            self._recover_interrupted_on_startup()

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def backup(self, dest: Path | None = None) -> Path:
        with self._lock:
            if self._conn is None:
                raise RuntimeError("task queue store not initialized")
            target = dest or (self.db_path.parent / f"task-queue-backup-{uuid.uuid4().hex[:8]}.sqlite3")
            target.parent.mkdir(parents=True, exist_ok=True)
            backup_conn = sqlite3.connect(str(target))
            try:
                self._conn.backup(backup_conn)
            finally:
                backup_conn.close()
            return target

    def _conn_required(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("task queue store not initialized")
        return self._conn

    def _migrate_schema(self) -> None:
        conn = self._conn_required()
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_meta'"
        ).fetchone()
        if row is None:
            conn.executescript(
                """
                CREATE TABLE schema_meta (version INTEGER NOT NULL);
                INSERT INTO schema_meta(version) VALUES (1);

                CREATE TABLE queue_control (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    paused INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL
                );
                INSERT INTO queue_control(id, paused, updated_at) VALUES (1, 0, '');

                CREATE TABLE tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    status TEXT NOT NULL,
                    agent_id TEXT NOT NULL DEFAULT 'default',
                    priority INTEGER NOT NULL DEFAULT 0,
                    scheduled_at TEXT NOT NULL DEFAULT '',
                    max_attempts INTEGER NOT NULL DEFAULT 3,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    backoff_strategy TEXT NOT NULL DEFAULT 'exponential',
                    backoff_base_seconds INTEGER NOT NULL DEFAULT 5,
                    backoff_max_seconds INTEGER NOT NULL DEFAULT 300,
                    timeout_seconds INTEGER NOT NULL DEFAULT 600,
                    idempotency_key TEXT NOT NULL DEFAULT '',
                    thread_id TEXT NOT NULL DEFAULT '',
                    trace_id TEXT NOT NULL DEFAULT '',
                    run_id TEXT NOT NULL DEFAULT '',
                    result TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    gateway TEXT NOT NULL DEFAULT '',
                    gateway_user TEXT NOT NULL DEFAULT '',
                    source TEXT NOT NULL DEFAULT 'api',
                    revision INTEGER NOT NULL DEFAULT 1,
                    retry_after TEXT NOT NULL DEFAULT '',
                    run_snapshot_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    lease_owner TEXT NOT NULL DEFAULT '',
                    lease_expires_at TEXT NOT NULL DEFAULT '',
                    migrated_from_json INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX idx_tasks_status ON tasks(status);
                CREATE INDEX idx_tasks_scheduled ON tasks(scheduled_at);
                CREATE INDEX idx_tasks_idempotency ON tasks(idempotency_key);
                CREATE INDEX idx_tasks_created ON tasks(created_at);

                CREATE TABLE task_attempts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL REFERENCES tasks(id) ON DELETE CASCADE,
                    attempt_number INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    worker_id TEXT NOT NULL DEFAULT '',
                    run_id TEXT NOT NULL DEFAULT '',
                    trace_id TEXT NOT NULL DEFAULT '',
                    thread_id TEXT NOT NULL DEFAULT '',
                    result_summary TEXT NOT NULL DEFAULT '',
                    error_summary TEXT NOT NULL DEFAULT '',
                    error_category TEXT NOT NULL DEFAULT '',
                    started_at TEXT NOT NULL DEFAULT '',
                    finished_at TEXT NOT NULL DEFAULT '',
                    duration_ms INTEGER NOT NULL DEFAULT 0,
                    UNIQUE(task_id, attempt_number)
                );
                CREATE INDEX idx_attempts_task ON task_attempts(task_id);

                CREATE TABLE task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE INDEX idx_events_task ON task_events(task_id, id);

                CREATE TABLE idempotency_keys (
                    key TEXT PRIMARY KEY,
                    task_id TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                """
            )
            conn.commit()
            return
        version = conn.execute("SELECT version FROM schema_meta LIMIT 1").fetchone()[0]
        if version < SCHEMA_VERSION:
            conn.execute("UPDATE schema_meta SET version = ?", (SCHEMA_VERSION,))
            conn.commit()

    def _recover_interrupted_on_startup(self) -> None:
        conn = self._conn_required()
        now = utc_now_iso()
        rows = conn.execute(
            "SELECT id FROM tasks WHERE status IN ('running', 'cancelling', 'leased')"
        ).fetchall()
        if not rows:
            return
        for row in rows:
            task_id = row["id"]
            conn.execute(
                """
                UPDATE tasks
                SET status = 'interrupted',
                    error = CASE WHEN error = '' THEN 'Task interrupted by service restart' ELSE error END,
                    lease_owner = '',
                    lease_expires_at = '',
                    updated_at = ?,
                    revision = revision + 1
                WHERE id = ? AND status IN ('running', 'cancelling', 'leased')
                """,
                (now, task_id),
            )
            self._append_event(conn, task_id, "interrupted", {"reason": "startup_recovery"})
        conn.commit()

    def is_paused(self) -> bool:
        with self._lock:
            row = self._conn_required().execute(
                "SELECT paused FROM queue_control WHERE id = 1"
            ).fetchone()
            return bool(row and row["paused"])

    def set_paused(self, paused: bool) -> bool:
        with self._lock:
            conn = self._conn_required()
            now = utc_now_iso()
            conn.execute(
                "UPDATE queue_control SET paused = ?, updated_at = ? WHERE id = 1",
                (1 if paused else 0, now),
            )
            conn.commit()
            return paused

    def create_task(self, payload: dict[str, Any]) -> TaskRecord:
        with self._lock:
            conn = self._conn_required()
            now = utc_now_iso()
            task_id = payload.get("id") or uuid.uuid4().hex[:12]
            idempotency_key = str(payload.get("idempotency_key") or "")
            if idempotency_key:
                existing = self.find_by_idempotency_key(idempotency_key)
                if existing:
                    return existing
            scheduled_at = str(payload.get("scheduled_at") or "")
            status = TaskStatus.SCHEDULED if scheduled_at else TaskStatus.QUEUED
            metadata = sanitize_metadata(payload.get("metadata") or {})
            agent_id = str(payload.get("agent_id") or metadata.get("agent_id") or "default")
            metadata["agent_id"] = agent_id
            snapshot = sanitize_snapshot(payload.get("run_snapshot") or {})
            conn.execute(
                """
                INSERT INTO tasks (
                    id, title, prompt, status, agent_id, priority, scheduled_at, max_attempts,
                    backoff_strategy, backoff_base_seconds, backoff_max_seconds, timeout_seconds,
                    idempotency_key, thread_id, gateway, gateway_user, source, metadata_json,
                    run_snapshot_json, created_at, updated_at, revision
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    task_id,
                    sanitize_text(str(payload.get("title") or ""), max_chars=512),
                    sanitize_text(str(payload.get("prompt") or ""), max_chars=8000),
                    status.value,
                    agent_id,
                    int(payload.get("priority") or 0),
                    scheduled_at,
                    int(payload.get("max_attempts") or settings.task_queue_default_max_attempts),
                    str(payload.get("backoff_strategy") or "exponential"),
                    int(payload.get("backoff_base_seconds") or settings.task_queue_backoff_base_seconds),
                    int(payload.get("backoff_max_seconds") or settings.task_queue_backoff_max_seconds),
                    int(payload.get("timeout_seconds") or settings.task_queue_default_timeout_seconds),
                    idempotency_key,
                    str(payload.get("thread_id") or uuid.uuid4().hex[:16]),
                    str(payload.get("gateway") or ""),
                    str(payload.get("gateway_user") or ""),
                    str(payload.get("source") or "api"),
                    json.dumps(metadata, ensure_ascii=False),
                    json.dumps(snapshot, ensure_ascii=False),
                    now,
                    now,
                ),
            )
            if idempotency_key:
                expires = (
                    datetime.now(timezone.utc)
                    + timedelta(seconds=settings.task_queue_idempotency_window_seconds)
                ).isoformat()
                conn.execute(
                    """
                    INSERT OR IGNORE INTO idempotency_keys(key, task_id, created_at, expires_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (idempotency_key, task_id, now, expires),
                )
            self._append_event(conn, task_id, "created", {"status": status.value})
            conn.commit()
            return self.get_task(task_id)  # type: ignore[return-value]

    def find_by_idempotency_key(self, key: str) -> TaskRecord | None:
        with self._lock:
            conn = self._conn_required()
            now = utc_now_iso()
            row = conn.execute(
                """
                SELECT task_id FROM idempotency_keys
                WHERE key = ? AND expires_at >= ?
                """,
                (key, now),
            ).fetchone()
            if not row:
                return None
            return self.get_task(row["task_id"])

    def get_task(self, task_id: str) -> TaskRecord | None:
        with self._lock:
            row = self._conn_required().execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return _row_to_task(row) if row else None

    def list_tasks(
        self,
        *,
        status: str | None = None,
        agent_id: str | None = None,
        source: str | None = None,
        query: str | None = None,
        created_after: str | None = None,
        created_before: str | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> tuple[list[TaskRecord], str | None]:
        with self._lock:
            clauses: list[str] = []
            params: list[Any] = []
            if status:
                normalized = TaskStatus.from_legacy(status).value
                clauses.append("status = ?")
                params.append(normalized)
            if agent_id:
                clauses.append("agent_id = ?")
                params.append(agent_id)
            if source:
                clauses.append("source = ?")
                params.append(source)
            if created_after:
                clauses.append("created_at >= ?")
                params.append(created_after)
            if created_before:
                clauses.append("created_at <= ?")
                params.append(created_before)
            if query:
                like = f"%{query.strip()}%"
                clauses.append("(title LIKE ? OR prompt LIKE ? OR id LIKE ?)")
                params.extend([like, like, like])
            if cursor:
                clauses.append("(created_at < ? OR (created_at = ? AND id < ?))")
                cursor_created, _, cursor_id = cursor.partition("|")
                params.extend([cursor_created, cursor_created, cursor_id])
            where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
            params.append(max(1, min(limit, 200)))
            rows = self._conn_required().execute(
                f"""
                SELECT * FROM tasks
                {where}
                ORDER BY created_at DESC, id DESC
                LIMIT ?
                """,
                params,
            ).fetchall()
            tasks = [_row_to_task(row) for row in rows]
            next_cursor = None
            if len(tasks) == limit:
                last = tasks[-1]
                next_cursor = f"{last.created_at}|{last.id}"
            return tasks, next_cursor

    def count_by_status(self) -> dict[str, int]:
        with self._lock:
            rows = self._conn_required().execute(
                "SELECT status, COUNT(*) AS c FROM tasks GROUP BY status"
            ).fetchall()
            return {row["status"]: row["c"] for row in rows}

    def transition_status(
        self,
        task_id: str,
        new_status: TaskStatus,
        *,
        expected_statuses: set[TaskStatus] | None = None,
        revision: int | None = None,
        fields: dict[str, Any] | None = None,
    ) -> TaskRecord | None:
        with self._lock:
            conn = self._conn_required()
            task = self.get_task(task_id)
            if not task:
                return None
            if expected_statuses and task.status not in expected_statuses:
                return None
            if revision is not None and task.revision != revision:
                return None
            fields = fields or {}
            now = utc_now_iso()
            assignments = ["status = ?", "updated_at = ?", "revision = revision + 1"]
            params: list[Any] = [new_status.value, now]
            for key, value in fields.items():
                if key in {
                    "result",
                    "error",
                    "trace_id",
                    "run_id",
                    "thread_id",
                    "retry_after",
                    "lease_owner",
                    "lease_expires_at",
                    "attempt_count",
                    "run_snapshot_json",
                    "metadata_json",
                    "scheduled_at",
                }:
                    assignments.append(f"{key} = ?")
                    params.append(value)
            params.extend([task_id])
            if expected_statuses:
                placeholders = ",".join("?" for _ in expected_statuses)
                params.extend([s.value for s in expected_statuses])
                sql = f"""
                    UPDATE tasks SET {', '.join(assignments)}
                    WHERE id = ? AND status IN ({placeholders})
                """
            elif revision is not None:
                params.append(revision)
                sql = f"""
                    UPDATE tasks SET {', '.join(assignments)}
                    WHERE id = ? AND revision = ?
                """
            else:
                sql = f"UPDATE tasks SET {', '.join(assignments)} WHERE id = ?"
            cur = conn.execute(sql, params)
            if cur.rowcount != 1:
                conn.rollback()
                return None
            self._append_event(
                conn,
                task_id,
                "status_changed",
                {"from": task.status.value, "to": new_status.value},
            )
            conn.commit()
            return self.get_task(task_id)

    def claim_next_task(self, worker_id: str, lease_seconds: int) -> TaskRecord | None:
        with self._lock:
            if self.is_paused():
                return None
            conn = self._conn_required()
            now_dt = datetime.now(timezone.utc)
            now = now_dt.isoformat()
            lease_until = (now_dt + timedelta(seconds=lease_seconds)).isoformat()
            conn.execute(
                """
                UPDATE tasks
                SET status = 'queued', updated_at = ?
                WHERE status = 'scheduled' AND scheduled_at != '' AND scheduled_at <= ?
                """,
                (now, now),
            )
            conn.execute(
                """
                UPDATE tasks
                SET status = 'queued', retry_after = '', updated_at = ?
                WHERE status = 'retry_wait' AND retry_after != '' AND retry_after <= ?
                """,
                (now, now),
            )
            conn.execute(
                """
                UPDATE tasks
                SET status = 'queued', lease_owner = '', lease_expires_at = '', updated_at = ?
                WHERE status = 'leased' AND lease_expires_at != '' AND lease_expires_at <= ?
                """,
                (now, now),
            )
            row = conn.execute(
                """
                SELECT * FROM tasks
                WHERE status = 'queued'
                ORDER BY priority DESC, created_at ASC
                LIMIT 1
                """
            ).fetchone()
            if not row:
                conn.commit()
                return None
            task_id = row["id"]
            cur = conn.execute(
                """
                UPDATE tasks
                SET status = 'leased', lease_owner = ?, lease_expires_at = ?, updated_at = ?, revision = revision + 1
                WHERE id = ? AND status = 'queued'
                """,
                (worker_id, lease_until, now, task_id),
            )
            if cur.rowcount != 1:
                conn.rollback()
                return None
            self._append_event(conn, task_id, "leased", {"worker_id": worker_id})
            conn.commit()
            return self.get_task(task_id)

    def count_active_runs(self) -> dict[str, int]:
        with self._lock:
            conn = self._conn_required()
            global_count = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE status IN ('leased', 'running', 'cancelling')"
            ).fetchone()[0]
            agent_rows = conn.execute(
                """
                SELECT agent_id, COUNT(*) AS c FROM tasks
                WHERE status IN ('leased', 'running', 'cancelling')
                GROUP BY agent_id
                """
            ).fetchall()
            provider_rows = conn.execute(
                """
                SELECT json_extract(run_snapshot_json, '$.connection_id') AS connection_id, COUNT(*) AS c
                FROM tasks
                WHERE status IN ('leased', 'running', 'cancelling')
                  AND json_extract(run_snapshot_json, '$.connection_id') IS NOT NULL
                  AND json_extract(run_snapshot_json, '$.connection_id') != ''
                GROUP BY connection_id
                """
            ).fetchall()
            return {
                "global": global_count,
                "agents": {row["agent_id"]: row["c"] for row in agent_rows},
                "providers": {str(row["connection_id"]): row["c"] for row in provider_rows},
            }

    def create_attempt(self, task_id: str, attempt_number: int, worker_id: str) -> TaskAttempt:
        with self._lock:
            conn = self._conn_required()
            now = utc_now_iso()
            cur = conn.execute(
                """
                INSERT INTO task_attempts (
                    task_id, attempt_number, status, worker_id, started_at
                ) VALUES (?, ?, 'running', ?, ?)
                """,
                (task_id, attempt_number, worker_id, now),
            )
            conn.execute(
                "UPDATE tasks SET attempt_count = ?, updated_at = ? WHERE id = ?",
                (attempt_number, now, task_id),
            )
            conn.commit()
            return self.get_attempt(int(cur.lastrowid))  # type: ignore[return-value]

    def finish_attempt(
        self,
        attempt_id: int,
        *,
        status: str,
        result_summary: str = "",
        error_summary: str = "",
        error_category: str = "",
        run_id: str = "",
        trace_id: str = "",
        thread_id: str = "",
    ) -> None:
        with self._lock:
            conn = self._conn_required()
            row = conn.execute(
                "SELECT started_at FROM task_attempts WHERE id = ?", (attempt_id,)
            ).fetchone()
            finished = utc_now_iso()
            duration_ms = 0
            if row and row["started_at"]:
                try:
                    start = datetime.fromisoformat(row["started_at"])
                    end = datetime.fromisoformat(finished)
                    duration_ms = max(0, int((end - start).total_seconds() * 1000))
                except ValueError:
                    duration_ms = 0
            conn.execute(
                """
                UPDATE task_attempts
                SET status = ?, result_summary = ?, error_summary = ?, error_category = ?,
                    run_id = ?, trace_id = ?, thread_id = ?, finished_at = ?, duration_ms = ?
                WHERE id = ?
                """,
                (
                    status,
                    sanitize_text(result_summary, max_chars=settings.task_queue_result_max_chars),
                    sanitize_text(error_summary, max_chars=settings.task_queue_error_max_chars),
                    error_category,
                    run_id,
                    trace_id,
                    thread_id,
                    finished,
                    duration_ms,
                    attempt_id,
                ),
            )
            conn.commit()

    def get_attempt(self, attempt_id: int) -> TaskAttempt | None:
        with self._lock:
            row = self._conn_required().execute(
                "SELECT * FROM task_attempts WHERE id = ?", (attempt_id,)
            ).fetchone()
            if not row:
                return None
            return TaskAttempt(
                id=row["id"],
                task_id=row["task_id"],
                attempt_number=row["attempt_number"],
                status=row["status"],
                worker_id=row["worker_id"],
                run_id=row["run_id"],
                trace_id=row["trace_id"],
                thread_id=row["thread_id"],
                result_summary=row["result_summary"],
                error_summary=row["error_summary"],
                error_category=row["error_category"],
                started_at=row["started_at"],
                finished_at=row["finished_at"],
                duration_ms=row["duration_ms"],
            )

    def list_attempts(self, task_id: str) -> list[TaskAttempt]:
        with self._lock:
            rows = self._conn_required().execute(
                "SELECT * FROM task_attempts WHERE task_id = ? ORDER BY attempt_number ASC",
                (task_id,),
            ).fetchall()
            return [
                TaskAttempt(
                    id=row["id"],
                    task_id=row["task_id"],
                    attempt_number=row["attempt_number"],
                    status=row["status"],
                    worker_id=row["worker_id"],
                    run_id=row["run_id"],
                    trace_id=row["trace_id"],
                    thread_id=row["thread_id"],
                    result_summary=row["result_summary"],
                    error_summary=row["error_summary"],
                    error_category=row["error_category"],
                    started_at=row["started_at"],
                    finished_at=row["finished_at"],
                    duration_ms=row["duration_ms"],
                )
                for row in rows
            ]

    def list_events(self, task_id: str, after_id: int = 0, limit: int = 200) -> list[TaskEvent]:
        with self._lock:
            rows = self._conn_required().execute(
                """
                SELECT * FROM task_events
                WHERE task_id = ? AND id > ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (task_id, after_id, max(1, min(limit, 500))),
            ).fetchall()
            return [
                TaskEvent(
                    id=row["id"],
                    task_id=row["task_id"],
                    event_type=row["event_type"],
                    payload_json=row["payload_json"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    def list_all_events(self, after_id: int = 0, limit: int = 200) -> list[TaskEvent]:
        with self._lock:
            rows = self._conn_required().execute(
                """
                SELECT * FROM task_events
                WHERE id > ?
                ORDER BY id ASC
                LIMIT ?
                """,
                (after_id, max(1, min(limit, 500))),
            ).fetchall()
            return [
                TaskEvent(
                    id=row["id"],
                    task_id=row["task_id"],
                    event_type=row["event_type"],
                    payload_json=row["payload_json"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    def _append_event(
        self,
        conn: sqlite3.Connection,
        task_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> None:
        conn.execute(
            """
            INSERT INTO task_events (task_id, event_type, payload_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (task_id, event_type, json.dumps(payload, ensure_ascii=False), utc_now_iso()),
        )

    def update_task_fields(self, task_id: str, *, revision: int, fields: dict[str, Any]) -> TaskRecord | None:
        allowed = {"title", "prompt", "priority", "scheduled_at", "max_attempts", "metadata_json"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return self.get_task(task_id)
        with self._lock:
            conn = self._conn_required()
            assignments = [f"{key} = ?" for key in updates]
            params = list(updates.values())
            now = utc_now_iso()
            assignments.extend(["updated_at = ?", "revision = revision + 1"])
            params.extend([now, task_id, revision])
            cur = conn.execute(
                f"""
                UPDATE tasks SET {', '.join(assignments)}
                WHERE id = ? AND revision = ? AND status IN ('queued', 'scheduled')
                """,
                params,
            )
            if cur.rowcount != 1:
                conn.rollback()
                return None
            self._append_event(conn, task_id, "updated", {"fields": list(updates.keys())})
            conn.commit()
            return self.get_task(task_id)

    def metrics_snapshot(self) -> dict[str, Any]:
        with self._lock:
            conn = self._conn_required()
            status_counts = self.count_by_status()
            depth = status_counts.get("queued", 0) + status_counts.get("scheduled", 0) + status_counts.get("retry_wait", 0)
            dead_letter = status_counts.get("dead_letter", 0)
            retry_total = conn.execute(
                "SELECT COUNT(*) FROM task_attempts WHERE status IN ('failed', 'retry')"
            ).fetchone()[0]
            lease_reclaimed = conn.execute(
                "SELECT COUNT(*) FROM task_events WHERE event_type = 'lease_reclaimed'"
            ).fetchone()[0]
            return {
                "queue_depth": depth,
                "status_counts": status_counts,
                "dead_letter_count": dead_letter,
                "retry_total": retry_total,
                "lease_reclaimed_total": lease_reclaimed,
                "paused": self.is_paused(),
            }
