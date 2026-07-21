"""SQLite persistent memory repository with schema migration and optional FTS5."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.memory.models import MemoryRecord, MemorySearchFilters

SCHEMA_VERSION = 1


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_content(text: str) -> str:
    return " ".join(text.strip().lower().split())


def _query_tokens(query: str) -> list[str]:
    tokens: list[str] = []
    for part in re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z0-9_]+", query.lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", part):
            if len(part) >= 2:
                tokens.append(part)
            for index in range(len(part) - 1):
                gram = part[index : index + 2]
                if len(gram) >= 2:
                    tokens.append(gram)
        elif len(part) >= 2:
            tokens.append(part)
    return list(dict.fromkeys(tokens))[:16]


class MemorySqliteRepository:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or (settings.memory_sqlite_path / "memories.sqlite3")
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None
        self._fts_enabled = False
        self._error = ""
        self._closed = False

    def initialize(self) -> None:
        with self._lock:
            self._closed = False
            self._error = ""
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._migrate()
            self._fts_enabled = self._ensure_fts()

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None
            self._closed = True

    def backup(self, dest: Path | None = None) -> Path:
        with self._lock:
            if self._conn is None:
                raise RuntimeError("memory repository 未初始化")
            target = dest or (self.db_path.parent / f"memories-backup-{uuid.uuid4().hex[:8]}.sqlite3")
            target.parent.mkdir(parents=True, exist_ok=True)
            backup_conn = sqlite3.connect(str(target))
            try:
                self._conn.backup(backup_conn)
            finally:
                backup_conn.close()
            return target

    def health(self) -> dict[str, Any]:
        writable = False
        if self._conn is not None and not self._closed:
            try:
                self._conn.execute("SELECT 1")
                writable = self.db_path.parent.exists() and self._is_writable()
            except sqlite3.Error as exc:
                self._error = str(exc)
        status = "error" if self._error else ("closed" if self._closed else "ready")
        return {
            "status": status,
            "backend": "sqlite",
            "persistent": True,
            "schema_version": SCHEMA_VERSION,
            "fts_enabled": self._fts_enabled,
            "writable": writable,
            "error": self._error,
        }

    def _is_writable(self) -> bool:
        probe = self.db_path.parent / ".write_probe"
        try:
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return True
        except OSError:
            return False

    def _migrate(self) -> None:
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_meta'"
        ).fetchone()
        if row is None:
            self._conn.executescript(
                """
                CREATE TABLE schema_meta (version INTEGER NOT NULL);
                INSERT INTO schema_meta(version) VALUES (0);

                CREATE TABLE memories (
                    id TEXT PRIMARY KEY,
                    agent_id TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    thread_id TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '[]',
                    source_type TEXT NOT NULL DEFAULT 'user_chat',
                    source_thread TEXT NOT NULL DEFAULT '',
                    source_trace TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'active',
                    content_norm TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_used_at TEXT NOT NULL DEFAULT '',
                    use_count INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX idx_memories_agent_status ON memories(agent_id, status);
                CREATE INDEX idx_memories_agent_scope ON memories(agent_id, scope, thread_id);
                CREATE INDEX idx_memories_updated ON memories(updated_at DESC);
                """
            )
        current = int(self._conn.execute("SELECT version FROM schema_meta").fetchone()[0])
        if current < SCHEMA_VERSION:
            self._conn.execute("UPDATE schema_meta SET version = ?", (SCHEMA_VERSION,))
        self._conn.commit()

    def _ensure_fts(self) -> bool:
        assert self._conn is not None
        try:
            self._conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
                    memory_id UNINDEXED,
                    agent_id UNINDEXED,
                    content,
                    summary,
                    tags,
                    tokenize='unicode61'
                )
                """
            )
            self._conn.commit()
            self._rebuild_fts()
            return True
        except sqlite3.Error:
            return False

    def _rebuild_fts(self) -> None:
        if not self._fts_enabled or self._conn is None:
            return
        self._conn.execute("DELETE FROM memories_fts")
        rows = self._conn.execute(
            "SELECT id, agent_id, content, summary, tags FROM memories WHERE status != 'deleted'"
        ).fetchall()
        for row in rows:
            self._conn.execute(
                "INSERT INTO memories_fts(memory_id, agent_id, content, summary, tags) VALUES (?, ?, ?, ?, ?)",
                (row["id"], row["agent_id"], row["content"], row["summary"], row["tags"]),
            )
        self._conn.commit()

    def _sync_fts(self, record: MemoryRecord) -> None:
        if not self._fts_enabled or self._conn is None:
            return
        self._conn.execute("DELETE FROM memories_fts WHERE memory_id = ?", (record.id,))
        if record.status != "deleted":
            self._conn.execute(
                "INSERT INTO memories_fts(memory_id, agent_id, content, summary, tags) VALUES (?, ?, ?, ?, ?)",
                (
                    record.id,
                    record.agent_id,
                    record.content,
                    record.summary,
                    json.dumps(record.tags, ensure_ascii=False),
                ),
            )

    def _row_to_record(self, row: sqlite3.Row) -> MemoryRecord:
        tags_raw = row["tags"] or "[]"
        try:
            tags = json.loads(tags_raw)
        except json.JSONDecodeError:
            tags = []
        return MemoryRecord(
            id=row["id"],
            agent_id=row["agent_id"],
            scope=row["scope"],
            thread_id=row["thread_id"] or "",
            content=row["content"],
            summary=row["summary"],
            tags=tags if isinstance(tags, list) else [],
            source_type=row["source_type"],
            source_thread=row["source_thread"] or "",
            source_trace=row["source_trace"] or "",
            status=row["status"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            last_used_at=row["last_used_at"] or "",
            use_count=int(row["use_count"] or 0),
        )

    def count_for_agent(self, agent_id: str, *, status: str = "active") -> int:
        with self._lock:
            assert self._conn is not None
            row = self._conn.execute(
                "SELECT COUNT(*) AS c FROM memories WHERE agent_id = ? AND status = ?",
                (agent_id, status),
            ).fetchone()
            return int(row["c"])

    def count_non_deleted(self, agent_id: str) -> int:
        with self._lock:
            assert self._conn is not None
            row = self._conn.execute(
                "SELECT COUNT(*) AS c FROM memories WHERE agent_id = ? AND status != 'deleted'",
                (agent_id,),
            ).fetchone()
            return int(row["c"])

    def count_pending(self, agent_id: str) -> int:
        return self.count_for_agent(agent_id, status="pending")

    def get(self, agent_id: str, memory_id: str) -> MemoryRecord | None:
        with self._lock:
            assert self._conn is not None
            row = self._conn.execute(
                "SELECT * FROM memories WHERE agent_id = ? AND id = ? AND status != 'deleted'",
                (agent_id, memory_id),
            ).fetchone()
            return self._row_to_record(row) if row else None

    def find_duplicate(self, agent_id: str, content: str) -> MemoryRecord | None:
        norm = _normalize_content(content)
        if not norm:
            return None
        with self._lock:
            assert self._conn is not None
            row = self._conn.execute(
                """
                SELECT * FROM memories
                WHERE agent_id = ? AND content_norm = ? AND status IN ('active', 'pending')
                LIMIT 1
                """,
                (agent_id, norm),
            ).fetchone()
            return self._row_to_record(row) if row else None

    def insert(self, record: MemoryRecord) -> MemoryRecord:
        with self._lock:
            assert self._conn is not None
            now = _utc_now()
            record.created_at = record.created_at or now
            record.updated_at = record.updated_at or now
            norm = _normalize_content(record.content)
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                self._conn.execute(
                    """
                    INSERT INTO memories (
                        id, agent_id, scope, thread_id, content, summary, tags,
                        source_type, source_thread, source_trace, status, content_norm,
                        created_at, updated_at, last_used_at, use_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        record.id,
                        record.agent_id,
                        record.scope,
                        record.thread_id,
                        record.content,
                        record.summary,
                        json.dumps(record.tags, ensure_ascii=False),
                        record.source_type,
                        record.source_thread,
                        record.source_trace,
                        record.status,
                        norm,
                        record.created_at,
                        record.updated_at,
                        record.last_used_at,
                        record.use_count,
                    ),
                )
                self._sync_fts(record)
                self._conn.commit()
            except sqlite3.Error as exc:
                self._conn.rollback()
                self._error = str(exc)
                raise
            return record

    def update(self, record: MemoryRecord) -> MemoryRecord:
        with self._lock:
            assert self._conn is not None
            record.updated_at = _utc_now()
            norm = _normalize_content(record.content)
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                self._conn.execute(
                    """
                    UPDATE memories SET
                        scope = ?, thread_id = ?, content = ?, summary = ?, tags = ?,
                        source_type = ?, source_thread = ?, source_trace = ?, status = ?,
                        content_norm = ?, updated_at = ?, last_used_at = ?, use_count = ?
                    WHERE agent_id = ? AND id = ?
                    """,
                    (
                        record.scope,
                        record.thread_id,
                        record.content,
                        record.summary,
                        json.dumps(record.tags, ensure_ascii=False),
                        record.source_type,
                        record.source_thread,
                        record.source_trace,
                        record.status,
                        norm,
                        record.updated_at,
                        record.last_used_at,
                        record.use_count,
                        record.agent_id,
                        record.id,
                    ),
                )
                self._sync_fts(record)
                self._conn.commit()
            except sqlite3.Error as exc:
                self._conn.rollback()
                self._error = str(exc)
                raise
            return record

    def mark_deleted(self, agent_id: str, memory_id: str) -> bool:
        record = self.get(agent_id, memory_id)
        if record is None:
            return False
        record.status = "deleted"
        record.content = ""
        record.summary = ""
        record.tags = []
        self.update(record)
        return True

    def bulk_delete(
        self,
        agent_id: str,
        *,
        status: str = "",
        scope: str = "",
        thread_id: str = "",
        ids: list[str] | None = None,
    ) -> int:
        if not status and not scope and not thread_id and not ids:
            raise ValueError("批量删除必须提供筛选条件")
        clauses = ["agent_id = ?", "status != 'deleted'"]
        params: list[Any] = [agent_id]
        if status:
            clauses.append("status = ?")
            params.append(status)
        if scope:
            clauses.append("scope = ?")
            params.append(scope)
        if thread_id:
            clauses.append("thread_id = ?")
            params.append(thread_id)
        if ids:
            placeholders = ",".join("?" for _ in ids)
            clauses.append(f"id IN ({placeholders})")
            params.extend(ids)
        sql = f"UPDATE memories SET status = 'deleted', content = '', summary = '', tags = '[]', updated_at = ? WHERE {' AND '.join(clauses)}"
        now = _utc_now()
        with self._lock:
            assert self._conn is not None
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                cur = self._conn.execute(sql, [now, *params])
                if self._fts_enabled:
                    if ids:
                        for memory_id in ids:
                            self._conn.execute("DELETE FROM memories_fts WHERE memory_id = ?", (memory_id,))
                    else:
                        rows = self._conn.execute(
                            f"SELECT id FROM memories WHERE {' AND '.join(clauses)}",
                            params,
                        ).fetchall()
                        for row in rows:
                            self._conn.execute("DELETE FROM memories_fts WHERE memory_id = ?", (row["id"],))
                self._conn.commit()
                return int(cur.rowcount)
            except sqlite3.Error as exc:
                self._conn.rollback()
                self._error = str(exc)
                raise

    def list_memories(
        self,
        agent_id: str,
        *,
        filters: MemorySearchFilters | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> tuple[list[MemoryRecord], int]:
        filters = filters or MemorySearchFilters()
        clauses = ["agent_id = ?", "status != 'deleted'"]
        params: list[Any] = [agent_id]
        if filters.status:
            clauses.append("status = ?")
            params.append(filters.status)
        if filters.scope:
            clauses.append("scope = ?")
            params.append(filters.scope)
        if filters.thread_id:
            clauses.append("thread_id = ?")
            params.append(filters.thread_id)
        if filters.tag:
            clauses.append("tags LIKE ?")
            params.append(f'%"{filters.tag}"%')

        q = filters.q.strip()
        tokens = _query_tokens(q)
        if q and self._fts_enabled:
            fts_ids = self._search_fts(agent_id, q, limit=settings.memory_page_max_size)
            if not fts_ids and tokens:
                merged: list[str] = []
                for token in tokens:
                    merged.extend(self._search_fts(agent_id, token, limit=settings.memory_page_max_size))
                fts_ids = list(dict.fromkeys(merged))
            if fts_ids:
                placeholders = ",".join("?" for _ in fts_ids)
                clauses.append(f"id IN ({placeholders})")
                params.extend(fts_ids)
            elif tokens:
                token_clauses = []
                for token in tokens:
                    like = f"%{token[: settings.memory_query_max_chars]}%"
                    token_clauses.append("(content LIKE ? OR summary LIKE ? OR tags LIKE ?)")
                    params.extend([like, like, like])
                clauses.append(f"({' OR '.join(token_clauses)})")
        elif q and tokens:
            token_clauses = []
            for token in tokens:
                like = f"%{token[: settings.memory_query_max_chars]}%"
                token_clauses.append("(content LIKE ? OR summary LIKE ? OR tags LIKE ?)")
                params.extend([like, like, like])
            clauses.append(f"({' OR '.join(token_clauses)})")
        elif q:
            clauses.append("(content LIKE ? OR summary LIKE ? OR tags LIKE ?)")
            like = f"%{q[: settings.memory_query_max_chars]}%"
            params.extend([like, like, like])

        where = " AND ".join(clauses)
        with self._lock:
            assert self._conn is not None
            total = int(
                self._conn.execute(f"SELECT COUNT(*) AS c FROM memories WHERE {where}", params).fetchone()["c"]
            )
            rows = self._conn.execute(
                f"""
                SELECT * FROM memories WHERE {where}
                ORDER BY updated_at DESC
                LIMIT ? OFFSET ?
                """,
                [*params, limit, offset],
            ).fetchall()
            return [self._row_to_record(row) for row in rows], total

    def _search_fts(self, agent_id: str, query: str, *, limit: int) -> list[str]:
        assert self._conn is not None
        safe_query = query.replace('"', " ").strip()
        if not safe_query:
            return []
        try:
            rows = self._conn.execute(
                """
                SELECT memory_id FROM memories_fts
                WHERE agent_id = ? AND memories_fts MATCH ?
                LIMIT ?
                """,
                (agent_id, safe_query, limit),
            ).fetchall()
            return [row["memory_id"] for row in rows]
        except sqlite3.Error:
            return []

    def retrieve_for_context(
        self,
        agent_id: str,
        *,
        thread_id: str,
        query: str,
        limit: int,
    ) -> list[MemoryRecord]:
        filters = MemorySearchFilters(q=query[: settings.memory_query_max_chars])
        rows, _ = self.list_memories(agent_id, filters=filters, offset=0, limit=max(limit * 3, limit))
        selected: list[MemoryRecord] = []
        seen: set[str] = set()
        for row in rows:
            if row.status != "active":
                continue
            if row.scope == "thread" and row.thread_id and row.thread_id != thread_id:
                continue
            norm_key = _normalize_content(row.content)
            if norm_key in seen:
                continue
            seen.add(norm_key)
            selected.append(row)
            if len(selected) >= limit:
                break
        return selected

    def touch_usage(self, agent_id: str, memory_ids: list[str]) -> None:
        if not memory_ids:
            return
        now = _utc_now()
        with self._lock:
            assert self._conn is not None
            placeholders = ",".join("?" for _ in memory_ids)
            self._conn.execute(
                f"""
                UPDATE memories
                SET use_count = use_count + 1, last_used_at = ?, updated_at = ?
                WHERE agent_id = ? AND id IN ({placeholders}) AND status = 'active'
                """,
                [now, now, agent_id, *memory_ids],
            )
            self._conn.commit()

    def export_active(self, agent_id: str) -> list[dict[str, Any]]:
        rows, _ = self.list_memories(
            agent_id,
            filters=MemorySearchFilters(status="active"),
            offset=0,
            limit=settings.memory_max_per_agent,
        )
        return [row.to_public_dict() for row in rows]


memory_repository = MemorySqliteRepository()
