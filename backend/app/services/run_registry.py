"""In-process registry for cancellable Agent and background runs."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator, Coroutine

from app.core.observability import EventType, emit_event


class RunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"


TERMINAL_STATUSES = {RunStatus.CANCELLED, RunStatus.COMPLETED, RunStatus.FAILED}
_ALLOWED_TRANSITIONS = {
    RunStatus.PENDING: {RunStatus.RUNNING, RunStatus.CANCELLING, RunStatus.CANCELLED, RunStatus.FAILED},
    RunStatus.RUNNING: {RunStatus.CANCELLING, RunStatus.CANCELLED, RunStatus.COMPLETED, RunStatus.FAILED},
    RunStatus.CANCELLING: {RunStatus.CANCELLED},
}


@dataclass
class RunEntry:
    agent_id: str
    thread_id: str
    run_id: str
    task_id: str = ""
    trace_id: str = ""
    status: RunStatus = RunStatus.PENDING
    task: asyncio.Task[Any] | None = field(default=None, repr=False)
    cancel_token: asyncio.Event = field(default_factory=asyncio.Event, repr=False)
    sequence: int = 0


@dataclass(frozen=True)
class CancelResult:
    found: bool
    cancelled: bool
    status: RunStatus | None
    run_id: str = ""
    detail: str = ""


class RunRegistry:
    """Track active runs and retain a small terminal history for clear responses."""

    def __init__(self, terminal_limit: int = 256) -> None:
        self._runs: OrderedDict[str, RunEntry] = OrderedDict()
        self._task_runs: dict[str, str] = {}
        self._active: dict[tuple[str, str], set[str]] = {}
        self._sequence = 0
        self._terminal_limit = terminal_limit

    def _register(self, entry: RunEntry) -> RunEntry:
        existing = self._runs.get(entry.run_id)
        if existing is not None and existing.status not in TERMINAL_STATUSES:
            raise RuntimeError(f"Run already active: {entry.run_id}")
        self._sequence += 1
        entry.sequence = self._sequence
        self._runs[entry.run_id] = entry
        self._active.setdefault((entry.agent_id, entry.thread_id), set()).add(entry.run_id)
        if entry.task_id:
            self._task_runs[entry.task_id] = entry.run_id
        self._emit_transition(entry, None, RunStatus.PENDING)
        return entry

    def _emit_transition(
        self,
        entry: RunEntry,
        previous: RunStatus | None,
        current: RunStatus,
    ) -> None:
        emit_event(
            EventType.RUN_STATUS,
            {
                "agent_id": entry.agent_id,
                "thread_id": entry.thread_id,
                "task_id": entry.task_id,
                "previous_status": previous.value if previous else "",
                "status": current.value,
            },
            trace_id=entry.trace_id or None,
            run_id=entry.run_id,
        )

    def transition(self, entry: RunEntry, status: RunStatus) -> bool:
        if entry.status == status:
            return True
        if status not in _ALLOWED_TRANSITIONS.get(entry.status, set()):
            return False
        previous = entry.status
        entry.status = status
        self._emit_transition(entry, previous, status)
        if status in TERMINAL_STATUSES:
            self._deactivate(entry)
        return True

    def _deactivate(self, entry: RunEntry) -> None:
        active = self._active.get((entry.agent_id, entry.thread_id))
        if active is not None:
            active.discard(entry.run_id)
            if not active:
                self._active.pop((entry.agent_id, entry.thread_id), None)
        if entry.task_id:
            self._task_runs.pop(entry.task_id, None)
        entry.task = None
        terminal_ids = [run_id for run_id, item in self._runs.items() if item.status in TERMINAL_STATUSES]
        for run_id in terminal_ids[: -self._terminal_limit]:
            self._runs.pop(run_id, None)

    @asynccontextmanager
    async def track_current(
        self,
        *,
        agent_id: str,
        thread_id: str,
        run_id: str,
        task_id: str = "",
        trace_id: str = "",
    ) -> AsyncIterator[RunEntry]:
        current = asyncio.current_task()
        if current is None:
            raise RuntimeError("No current asyncio task")
        entry = self._register(
            RunEntry(
                agent_id=agent_id,
                thread_id=thread_id,
                run_id=run_id,
                task_id=task_id,
                trace_id=trace_id,
                task=current,
            )
        )
        self.transition(entry, RunStatus.RUNNING)
        try:
            yield entry
        except (asyncio.CancelledError, GeneratorExit):
            self.transition(entry, RunStatus.CANCELLED)
            raise
        except BaseException:
            self.transition(entry, RunStatus.FAILED)
            raise
        else:
            self.transition(entry, RunStatus.COMPLETED)

    def start(
        self,
        coroutine: Coroutine[Any, Any, Any],
        *,
        agent_id: str,
        thread_id: str,
        run_id: str,
        task_id: str = "",
        trace_id: str = "",
    ) -> RunEntry:
        entry = RunEntry(
            agent_id=agent_id,
            thread_id=thread_id,
            run_id=run_id,
            task_id=task_id,
            trace_id=trace_id,
        )

        async def runner() -> Any:
            self.transition(entry, RunStatus.RUNNING)
            try:
                result = await coroutine
            except asyncio.CancelledError:
                self.transition(entry, RunStatus.CANCELLED)
                raise
            except BaseException:
                self.transition(entry, RunStatus.FAILED)
                raise
            else:
                self.transition(entry, RunStatus.COMPLETED)
                return result

        task = asyncio.create_task(runner(), name=f"run:{run_id}")
        entry.task = task
        self._register(entry)

        def consume_exception(done: asyncio.Task[Any]) -> None:
            if done.cancelled():
                self.transition(entry, RunStatus.CANCELLED)
                coroutine.close()
            else:
                done.exception()

        task.add_done_callback(consume_exception)
        return entry

    def get(self, run_id: str) -> RunEntry | None:
        return self._runs.get(run_id)

    def active_for(self, agent_id: str, thread_id: str) -> RunEntry | None:
        run_ids = self._active.get((agent_id, thread_id), set())
        entries = [self._runs[run_id] for run_id in run_ids if run_id in self._runs]
        return max(entries, key=lambda item: item.sequence, default=None)

    async def cancel(
        self,
        *,
        run_id: str = "",
        task_id: str = "",
        agent_id: str = "",
        thread_id: str = "",
    ) -> CancelResult:
        entry = self._runs.get(run_id) if run_id else None
        if entry is None and task_id:
            mapped_run = self._task_runs.get(task_id, "")
            entry = self._runs.get(mapped_run)
        if entry is None and agent_id and thread_id:
            entry = self.active_for(agent_id, thread_id)
        if entry is None:
            return CancelResult(False, False, None, detail="No matching run")
        if agent_id and entry.agent_id != agent_id:
            return CancelResult(False, False, None, detail="No matching run")
        if thread_id and entry.thread_id != thread_id:
            return CancelResult(False, False, None, detail="No matching run")
        if entry.status == RunStatus.CANCELLED:
            return CancelResult(True, True, entry.status, entry.run_id, "Run already cancelled")
        if entry.status in {RunStatus.COMPLETED, RunStatus.FAILED}:
            return CancelResult(True, False, entry.status, entry.run_id, "Run already finished")

        self.transition(entry, RunStatus.CANCELLING)
        entry.cancel_token.set()
        task = entry.task
        if task is None:
            return CancelResult(True, False, entry.status, entry.run_id, "Run has no cancellable task")
        if task is asyncio.current_task():
            return CancelResult(True, False, entry.status, entry.run_id, "Run cannot cancel itself")
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        cancelled = entry.status == RunStatus.CANCELLED
        return CancelResult(
            True,
            cancelled,
            entry.status,
            entry.run_id,
            "Run cancelled" if cancelled else "Run did not confirm cancellation",
        )

    async def shutdown(self) -> None:
        active = [entry for entry in self._runs.values() if entry.status not in TERMINAL_STATUSES]
        await asyncio.gather(*(self.cancel(run_id=entry.run_id) for entry in active))

    def clear(self) -> None:
        self._runs.clear()
        self._task_runs.clear()
        self._active.clear()


run_registry = RunRegistry()
