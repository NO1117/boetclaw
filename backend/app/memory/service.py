"""Persistent memory business logic."""

from __future__ import annotations

import time
import uuid
from typing import Any

from app.core.config import settings
from app.core.observability import EventType, emit_event, get_logger
from app.memory.context_policy import should_persist_memory
from app.memory.extraction import should_extract_candidate, summarize_content
from app.memory.injection import (
    build_memory_context_block,
    inject_memory_into_user_content,
)
from app.memory.intent import parse_memory_intent
from app.memory.metrics import memory_metrics
from app.memory.models import (
    MemoryActionResult,
    MemoryAutoMode,
    MemoryCandidatePublic,
    MemoryContextSummary,
    MemoryRecord,
    MemorySearchFilters,
)
from app.memory.sensitive import contains_sensitive_content, reject_reason
from app.memory.sqlite_repo import memory_repository

logger = get_logger("memory_service")


class MemoryUnavailableError(RuntimeError):
    pass


class MemoryService:
    def __init__(self) -> None:
        self._enabled = False
        self._persistent = False
        self._backend = settings.memory_backend
        self._fallback = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def auto_mode(self) -> MemoryAutoMode:
        mode = (settings.memory_auto_mode or "review").strip().lower()
        if mode not in {"off", "review", "auto"}:
            return "review"
        return mode  # type: ignore[return-value]

    def initialize(self) -> None:
        backend = settings.memory_backend
        self._backend = backend
        if backend == "none":
            self._enabled = False
            self._persistent = False
            return
        if backend == "file":
            self._enabled = False
            self._persistent = False
            return
        if backend == "store":
            self._enabled = True
            self._persistent = False
            if settings.memory_allow_inmemory_fallback:
                from app.memory.store_backend import get_store

                get_store()
            return
        if backend == "sqlite":
            try:
                memory_repository.initialize()
                self._enabled = True
                self._persistent = True
            except Exception as exc:  # noqa: BLE001
                memory_metrics.inc("storage_errors")
                logger.error("memory_init_failed", error=str(exc))
                if settings.memory_allow_inmemory_fallback:
                    self._enabled = True
                    self._persistent = False
                    self._fallback = True
                else:
                    self._enabled = False
                    self._persistent = False
            return
        self._enabled = False
        self._persistent = False

    def close(self) -> None:
        if settings.memory_backend == "sqlite" and not self._fallback:
            memory_repository.close()

    def health(self) -> dict[str, Any]:
        if settings.memory_backend == "sqlite" and self._enabled and not self._fallback:
            status = memory_repository.health()
            status["mode"] = self.auto_mode
            status["allow_fallback"] = settings.memory_allow_inmemory_fallback
            return status
        return {
            "status": "ready" if self._enabled else "disabled",
            "backend": self._backend,
            "persistent": self._persistent,
            "schema_version": 0,
            "fts_enabled": False,
            "writable": False,
            "mode": self.auto_mode,
            "fallback": self._fallback,
            "error": "",
        }

    def _require_repo(self) -> None:
        if settings.memory_backend != "sqlite" or not self._enabled or self._fallback:
            raise MemoryUnavailableError("持久记忆未启用")
        if memory_repository._conn is None:  # noqa: SLF001
            raise MemoryUnavailableError("记忆仓库未初始化")

    def _validate_write(self, content: str, tags: list[str] | None = None) -> None:
        if not content.strip():
            raise ValueError("记忆内容不能为空")
        if len(content) > settings.memory_max_content_chars:
            raise ValueError(f"单条记忆超过 {settings.memory_max_content_chars} 字符限制")
        tag_list = tags or []
        if len(tag_list) > settings.memory_max_tags:
            raise ValueError(f"标签数量超过 {settings.memory_max_tags} 个限制")
        reason = reject_reason(content)
        if reason:
            raise ValueError(reason)

    def _new_id(self) -> str:
        return uuid.uuid4().hex[:16]

    def create_manual(
        self,
        *,
        agent_id: str,
        content: str,
        scope: str = "agent",
        thread_id: str = "",
        tags: list[str] | None = None,
        status: str = "active",
        source_type: str = "manual",
        source_thread: str = "",
        source_trace: str = "",
    ) -> MemoryRecord:
        self._require_repo()
        self._validate_write(content, tags)
        if memory_repository.count_non_deleted(agent_id) >= settings.memory_max_per_agent:
            raise ValueError(f"该 Agent 记忆已达上限 {settings.memory_max_per_agent}")
        duplicate = memory_repository.find_duplicate(agent_id, content)
        if duplicate:
            memory_metrics.inc("deduped")
            raise ValueError("已存在相同或近似记忆")
        record = MemoryRecord(
            id=self._new_id(),
            agent_id=agent_id,
            scope="thread" if scope == "thread" else "agent",
            thread_id=thread_id if scope == "thread" else "",
            content=content.strip(),
            summary=summarize_content(content),
            tags=tags or [],
            source_type=source_type,  # type: ignore[arg-type]
            source_thread=source_thread,
            source_trace=source_trace,
            status="active" if status == "active" else status,  # type: ignore[arg-type]
            created_at="",
            updated_at="",
        )
        saved = memory_repository.insert(record)
        memory_metrics.inc("created")
        emit_event(
            EventType.MEMORY_CREATED,
            {"memory_id": saved.id, "agent_id": agent_id, "scope": saved.scope, "status": saved.status},
        )
        return saved

    def get(self, agent_id: str, memory_id: str) -> MemoryRecord | None:
        self._require_repo()
        return memory_repository.get(agent_id, memory_id)

    def list_memories(
        self,
        agent_id: str,
        *,
        filters: MemorySearchFilters | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        self._require_repo()
        page = max(page, 1)
        page_size = min(max(page_size, 1), settings.memory_page_max_size)
        offset = (page - 1) * page_size
        rows, total = memory_repository.list_memories(
            agent_id,
            filters=filters,
            offset=offset,
            limit=page_size,
        )
        return {
            "items": [row.to_public_dict() for row in rows],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def update_memory(
        self,
        agent_id: str,
        memory_id: str,
        *,
        content: str | None = None,
        tags: list[str] | None = None,
        scope: str | None = None,
        thread_id: str | None = None,
        status: str | None = None,
    ) -> MemoryRecord:
        self._require_repo()
        record = memory_repository.get(agent_id, memory_id)
        if record is None:
            raise ValueError("记忆不存在")
        if content is not None:
            self._validate_write(content, tags or record.tags)
            record.content = content.strip()
            record.summary = summarize_content(record.content)
        if tags is not None:
            if len(tags) > settings.memory_max_tags:
                raise ValueError(f"标签数量超过 {settings.memory_max_tags} 个限制")
            record.tags = tags
        if scope is not None:
            record.scope = "thread" if scope == "thread" else "agent"
        if thread_id is not None:
            record.thread_id = thread_id
        if status is not None:
            record.status = status  # type: ignore[assignment]
        return memory_repository.update(record)

    def delete(self, agent_id: str, memory_id: str) -> bool:
        self._require_repo()
        ok = memory_repository.mark_deleted(agent_id, memory_id)
        if ok:
            memory_metrics.inc("deleted")
            emit_event(EventType.MEMORY_DELETED, {"memory_id": memory_id, "agent_id": agent_id})
        return ok

    def bulk_delete(
        self,
        agent_id: str,
        *,
        status: str = "",
        scope: str = "",
        thread_id: str = "",
        ids: list[str] | None = None,
    ) -> int:
        self._require_repo()
        count = memory_repository.bulk_delete(
            agent_id,
            status=status,
            scope=scope,
            thread_id=thread_id,
            ids=ids,
        )
        if count:
            memory_metrics.inc("deleted", count)
        return count

    def approve(self, agent_id: str, memory_id: str) -> MemoryRecord:
        self._require_repo()
        record = memory_repository.get(agent_id, memory_id)
        if record is None or record.status != "pending":
            raise ValueError("候选记忆不存在或不可审核")
        record.status = "active"
        saved = memory_repository.update(record)
        memory_metrics.inc("approved")
        emit_event(EventType.MEMORY_APPROVED, {"memory_id": saved.id, "agent_id": agent_id})
        return saved

    def reject(self, agent_id: str, memory_id: str) -> MemoryRecord:
        self._require_repo()
        record = memory_repository.get(agent_id, memory_id)
        if record is None or record.status != "pending":
            raise ValueError("候选记忆不存在或不可审核")
        record.status = "rejected"
        saved = memory_repository.update(record)
        memory_metrics.inc("rejected")
        emit_event(EventType.MEMORY_REJECTED, {"memory_id": saved.id, "agent_id": agent_id})
        return saved

    def export_memories(self, agent_id: str) -> dict[str, Any]:
        self._require_repo()
        return {
            "agent_id": agent_id,
            "exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "mode": self.auto_mode,
            "memories": memory_repository.export_active(agent_id),
        }

    def build_context_summary(self, agent_id: str, *, used_items: list[dict[str, Any]] | None = None) -> MemoryContextSummary:
        if not self._enabled or settings.memory_backend != "sqlite" or self._fallback:
            return MemoryContextSummary(
                mode=self.auto_mode,
                backend=self._backend,
                persistent=self._persistent,
                saved_count=0,
                pending_count=0,
                used_count=0,
                injected_chars=0,
                items=used_items or [],
            )
        saved = memory_repository.count_for_agent(agent_id, status="active")
        pending = memory_repository.count_pending(agent_id)
        used = used_items or []
        return MemoryContextSummary(
            mode=self.auto_mode,
            backend=self._backend,
            persistent=self._persistent,
            saved_count=saved,
            pending_count=pending,
            used_count=len(used),
            injected_chars=sum(len(str(item.get("summary", ""))) for item in used),
            items=used,
        )

    def prepare_chat_memory(
        self,
        *,
        agent_id: str,
        thread_id: str,
        message: str,
        source: str,
        trace_id: str,
        user_content: str | list[Any],
    ) -> tuple[str | list[Any], MemoryContextSummary, list[MemoryActionResult], list[MemoryCandidatePublic]]:
        actions: list[MemoryActionResult] = []
        candidates: list[MemoryCandidatePublic] = []
        empty_summary = self.build_context_summary(agent_id)
        if not self._enabled or settings.memory_backend != "sqlite" or self._fallback:
            return user_content, empty_summary, actions, candidates
        if not should_persist_memory(source):
            memory_metrics.inc("skipped")
            return user_content, empty_summary, actions, candidates

        intent = parse_memory_intent(message)
        if intent:
            try:
                if intent.kind == "remember":
                    record = self.create_manual(
                        agent_id=agent_id,
                        content=intent.content,
                        scope="agent",
                        source_type="user_explicit",
                        source_thread=thread_id,
                        source_trace=trace_id,
                    )
                    actions.append(
                        MemoryActionResult(
                            action="remember",
                            success=True,
                            memory_id=record.id,
                            message="已保存到长期记忆",
                        )
                    )
                else:
                    deleted = self._forget_by_content(agent_id, intent.content)
                    actions.append(
                        MemoryActionResult(
                            action="forget",
                            success=deleted > 0,
                            message="已删除匹配记忆" if deleted else "未找到匹配记忆",
                        )
                    )
            except ValueError as exc:
                action = "reject_sensitive" if "凭据" in str(exc) else "duplicate"
                actions.append(MemoryActionResult(action=action, success=False, message=str(exc)))

        start = time.perf_counter()
        records = memory_repository.retrieve_for_context(
            agent_id,
            thread_id=thread_id,
            query=message,
            limit=settings.memory_retrieval_max_items,
        )
        memory_metrics.add_retrieval_ms((time.perf_counter() - start) * 1000)
        memory_metrics.inc("retrieved")
        selected: list[MemoryRecord] = []
        total_chars = 0
        seen: set[str] = set()
        for record in records:
            norm = " ".join(record.content.strip().lower().split())
            if norm in seen:
                memory_metrics.inc("deduped")
                continue
            seen.add(norm)
            add_len = len(record.summary or record.content)
            if total_chars + add_len > settings.memory_retrieval_max_chars:
                break
            selected.append(record)
            total_chars += add_len
            if len(selected) >= settings.memory_retrieval_max_items:
                break

        if selected:
            memory_repository.touch_usage(agent_id, [item.id for item in selected])
            memory_metrics.inc("hits", len(selected))
            block = build_memory_context_block(selected)
            memory_metrics.inc("injected_items", len(selected))
            memory_metrics.inc("injected_chars", len(block))
            user_content = inject_memory_into_user_content(user_content, block)
            emit_event(
                EventType.MEMORY_RETRIEVED,
                {
                    "agent_id": agent_id,
                    "thread_id": thread_id,
                    "hit_count": len(selected),
                    "char_budget": settings.memory_retrieval_max_chars,
                },
                trace_id=trace_id,
            )
        used_items = [
            {
                "id": item.id,
                "scope": item.scope,
                "summary": item.summary,
                "source_type": item.source_type,
                "source_thread": item.source_thread,
            }
            for item in selected
        ]
        summary = self.build_context_summary(agent_id, used_items=used_items)

        if self.auto_mode != "off" and should_extract_candidate(message):
            candidate = self._build_candidate(
                agent_id=agent_id,
                thread_id=thread_id,
                message=message,
                trace_id=trace_id,
            )
            if candidate:
                candidates.append(candidate)

        return user_content, summary, actions, candidates

    def _build_candidate(
        self,
        *,
        agent_id: str,
        thread_id: str,
        message: str,
        trace_id: str,
    ) -> MemoryCandidatePublic | None:
        if contains_sensitive_content(message):
            memory_metrics.inc("skipped")
            return None
        if len(message) > settings.memory_max_content_chars:
            return None
        if memory_repository.find_duplicate(agent_id, message):
            memory_metrics.inc("deduped")
            return None
        status = "pending" if self.auto_mode == "review" else "active"
        record = MemoryRecord(
            id=self._new_id(),
            agent_id=agent_id,
            scope="agent",
            thread_id="",
            content=message.strip(),
            summary=summarize_content(message),
            tags=[],
            source_type="user_chat",
            source_thread=thread_id,
            source_trace=trace_id,
            status=status,  # type: ignore[arg-type]
            created_at="",
            updated_at="",
        )
        try:
            saved = memory_repository.insert(record)
        except Exception:
            memory_metrics.inc("storage_errors")
            return None
        memory_metrics.inc("candidates")
        if status == "active":
            memory_metrics.inc("created")
        emit_event(
            EventType.MEMORY_CANDIDATE,
            {"memory_id": saved.id, "agent_id": agent_id, "status": saved.status},
            trace_id=trace_id,
        )
        return MemoryCandidatePublic(
            id=saved.id,
            summary=saved.summary,
            content=saved.content,
            scope=saved.scope,
            source_type=saved.source_type,
            source_thread=saved.source_thread,
            source_trace=saved.source_trace,
        )

    def _forget_by_content(self, agent_id: str, needle: str) -> int:
        filters = MemorySearchFilters(q=needle[: settings.memory_query_max_chars])
        rows, _ = memory_repository.list_memories(agent_id, filters=filters, limit=20, offset=0)
        deleted = 0
        for row in rows:
            if needle.strip() in row.content or needle.strip() in row.summary:
                if memory_repository.mark_deleted(agent_id, row.id):
                    deleted += 1
        return deleted

memory_service = MemoryService()
