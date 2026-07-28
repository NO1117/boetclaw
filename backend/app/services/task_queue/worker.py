"""Background worker for durable task queue."""

from __future__ import annotations

import asyncio
import socket
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.config import settings
from app.core.observability import EventType, emit_event, new_run_id, new_trace_id
from app.services.run_registry import run_registry
from app.services.task_queue.models import BackoffStrategy, TaskStatus, utc_now_iso
from app.services.task_queue.retry import classify_error, compute_backoff_seconds, is_retryable
from app.services.task_queue.sanitizer import sanitize_text
from app.services.task_queue.store import TaskQueueStore


class TaskQueueWorker:
    def __init__(self, store: TaskQueueStore) -> None:
        self.store = store
        self.worker_id = f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}"
        self._task: asyncio.Task[Any] | None = None
        self._stop_event = asyncio.Event()
        self._drain_event = asyncio.Event()
        self._running_tasks: dict[str, asyncio.Task[Any]] = {}
        self._shutdown_started = False

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def start(self) -> None:
        if self.running:
            return
        self._stop_event.clear()
        self._drain_event.clear()
        self._shutdown_started = False
        self._task = asyncio.create_task(self._loop(), name="task-queue-worker")

    async def stop(self, *, grace_seconds: int | None = None) -> None:
        grace = grace_seconds if grace_seconds is not None else settings.task_queue_shutdown_grace_seconds
        self._shutdown_started = True
        self._stop_event.set()
        if self._task:
            try:
                await asyncio.wait_for(self._drain_event.wait(), timeout=grace)
            except asyncio.TimeoutError:
                pass
            if not self._task.done():
                self._task.cancel()
                with asyncio.suppress(asyncio.CancelledError):
                    await self._task
        for task_id, handle in list(self._running_tasks.items()):
            handle.cancel()
            await run_registry.cancel(task_id=task_id)
            self.store.transition_status(
                task_id,
                TaskStatus.INTERRUPTED,
                expected_statuses={TaskStatus.RUNNING, TaskStatus.CANCELLING, TaskStatus.LEASED},
                fields={"error": "Worker shutdown", "lease_owner": "", "lease_expires_at": ""},
            )
        self._running_tasks.clear()

    async def _loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                claimed = await self._maybe_claim_and_run()
                if not claimed:
                    await asyncio.sleep(settings.task_queue_poll_interval_seconds)
            self._drain_event.set()
        except asyncio.CancelledError:
            self._drain_event.set()
            raise

    async def _maybe_claim_and_run(self) -> bool:
        if self._shutdown_started:
            return False
        active = self.store.count_active_runs()
        if active["global"] >= settings.task_queue_global_concurrency:
            return False
        task = self.store.claim_next_task(self.worker_id, settings.task_queue_lease_seconds)
        if not task:
            return False
        agent_active = active["agents"].get(task.agent_id, 0)
        if agent_active >= settings.task_queue_agent_concurrency:
            self.store.transition_status(
                task.id,
                TaskStatus.QUEUED,
                expected_statuses={TaskStatus.LEASED},
                fields={"lease_owner": "", "lease_expires_at": ""},
            )
            return True
        connection_id = str(task.run_snapshot.get("connection_id") or "")
        if connection_id:
            provider_active = active["providers"].get(connection_id, 0)
            if provider_active >= settings.task_queue_provider_concurrency:
                self.store.transition_status(
                    task.id,
                    TaskStatus.QUEUED,
                    expected_statuses={TaskStatus.LEASED},
                    fields={"lease_owner": "", "lease_expires_at": ""},
                )
                return True
        handle = asyncio.create_task(self._execute(task.id), name=f"task-run:{task.id}")
        self._running_tasks[task.id] = handle
        handle.add_done_callback(lambda _t, tid=task.id: self._running_tasks.pop(tid, None))
        return True

    async def _execute(self, task_id: str) -> None:
        from app.core.agent import agent_manager

        task = self.store.get_task(task_id)
        if not task:
            return
        trace_id = new_trace_id()
        run_id = new_run_id()
        attempt_number = max(1, task.attempt_count + 1)
        attempt = self.store.create_attempt(task_id, attempt_number, self.worker_id)
        updated = self.store.transition_status(
            task_id,
            TaskStatus.RUNNING,
            expected_statuses={TaskStatus.LEASED},
            fields={
                "trace_id": trace_id,
                "run_id": run_id,
                "lease_owner": self.worker_id,
                "lease_expires_at": (
                    datetime.now(timezone.utc) + timedelta(seconds=settings.task_queue_lease_seconds)
                ).isoformat(),
            },
        )
        if not updated:
            return
        emit_event(
            EventType.RUN_STATUS,
            {
                "task_id": task_id,
                "thread_id": task.thread_id,
                "agent_id": task.agent_id,
                "previous_status": TaskStatus.LEASED.value,
                "status": TaskStatus.RUNNING.value,
            },
            trace_id=trace_id,
            run_id=run_id,
        )

        async def runner() -> None:
            try:
                result = await asyncio.wait_for(
                    agent_manager.invoke(
                        task.prompt,
                        task.thread_id,
                        trace_id=trace_id,
                        run_id=run_id,
                        task_id=task_id,
                        agent_id=task.agent_id,
                        well_id=str(task.metadata.get("well_id", "")),
                    ),
                    timeout=task.timeout_seconds,
                )
                response = sanitize_text(str(result.get("response", "")))
                self.store.finish_attempt(
                    attempt.id,
                    status="completed",
                    result_summary=response,
                    run_id=run_id,
                    trace_id=trace_id,
                    thread_id=task.thread_id,
                )
                self.store.transition_status(
                    task_id,
                    TaskStatus.COMPLETED,
                    expected_statuses={TaskStatus.RUNNING},
                    fields={
                        "result": response,
                        "error": "",
                        "lease_owner": "",
                        "lease_expires_at": "",
                    },
                )
            except asyncio.CancelledError:
                self.store.finish_attempt(
                    attempt.id,
                    status="cancelled",
                    error_summary="cancelled",
                    error_category="cancelled",
                    run_id=run_id,
                    trace_id=trace_id,
                    thread_id=task.thread_id,
                )
                self.store.transition_status(
                    task_id,
                    TaskStatus.CANCELLED,
                    expected_statuses={TaskStatus.RUNNING, TaskStatus.CANCELLING, TaskStatus.LEASED},
                    fields={"lease_owner": "", "lease_expires_at": ""},
                )
                raise
            except Exception as exc:  # noqa: BLE001
                category = classify_error(exc)
                error_text = sanitize_text(str(exc))
                self.store.finish_attempt(
                    attempt.id,
                    status="failed",
                    error_summary=error_text,
                    error_category=category.value,
                    run_id=run_id,
                    trace_id=trace_id,
                    thread_id=task.thread_id,
                )
                await self._handle_failure(task_id, attempt_number, category, error_text)

        run_registry.start(
            runner(),
            agent_id=task.agent_id,
            thread_id=task.thread_id,
            run_id=run_id,
            task_id=task_id,
            trace_id=trace_id,
        )

    async def _handle_failure(
        self,
        task_id: str,
        attempt_number: int,
        category,
        error_text: str,
    ) -> None:
        task = self.store.get_task(task_id)
        if not task:
            return
        if not is_retryable(category) or attempt_number >= task.max_attempts:
            target = TaskStatus.DEAD_LETTER if attempt_number >= task.max_attempts else TaskStatus.FAILED
            self.store.transition_status(
                task_id,
                target,
                expected_statuses={TaskStatus.RUNNING},
                fields={
                    "error": error_text,
                    "lease_owner": "",
                    "lease_expires_at": "",
                },
            )
            return
        delay = compute_backoff_seconds(
            strategy=BackoffStrategy(task.backoff_strategy),
            attempt_number=attempt_number,
            base_seconds=task.backoff_base_seconds,
            max_seconds=task.backoff_max_seconds,
        )
        retry_after = (datetime.now(timezone.utc) + timedelta(seconds=delay)).isoformat()
        self.store.transition_status(
            task_id,
            TaskStatus.RETRY_WAIT,
            expected_statuses={TaskStatus.RUNNING},
            fields={
                "error": error_text,
                "retry_after": retry_after,
                "lease_owner": "",
                "lease_expires_at": "",
            },
        )

    async def enqueue_existing(self, task_id: str) -> bool:
        task = self.store.get_task(task_id)
        if not task:
            return False
        if task.status not in {TaskStatus.QUEUED, TaskStatus.SCHEDULED, TaskStatus.RETRY_WAIT}:
            updated = self.store.transition_status(
                task_id,
                TaskStatus.QUEUED,
                expected_statuses={
                    TaskStatus.COMPLETED,
                    TaskStatus.FAILED,
                    TaskStatus.CANCELLED,
                    TaskStatus.DEAD_LETTER,
                    TaskStatus.INTERRUPTED,
                },
                fields={"retry_after": "", "error": "", "result": ""},
            )
            return updated is not None
        return True
