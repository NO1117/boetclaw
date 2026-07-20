"""PLAN-660: periodic idle eviction for loaded workspace agents."""

from __future__ import annotations

import asyncio


class _FakeManager:
    def __init__(self) -> None:
        self.calls = 0

    def evict_idle(self) -> list[str]:
        self.calls += 1
        return ["agent-a"]


def test_agent_idle_eviction_run_once():
    from app.services.agent_idle import AgentIdleEvictionService

    manager = _FakeManager()
    service = AgentIdleEvictionService(manager=manager)

    assert service.run_once() == ["agent-a"]
    assert manager.calls == 1


async def test_agent_idle_eviction_start_stop():
    from app.services.agent_idle import AgentIdleEvictionService

    manager = _FakeManager()
    service = AgentIdleEvictionService(manager=manager)

    service.start(interval_seconds=0.01)
    service.start(interval_seconds=0.01)
    assert service.running is True

    await asyncio.sleep(0.03)
    await service.stop()

    assert service.running is False
    assert manager.calls >= 1
