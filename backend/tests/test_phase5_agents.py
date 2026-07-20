"""Phase 5 tests: multi-agent workspace, routing, lazy load."""

import asyncio

import pytest


def test_route_priority():
    from app.agents.agent_context import resolve_agent_id

    class _State:
        agent_id = "from_state"

    class _Req:
        state = _State()

    assert resolve_agent_id(explicit="explicit") == "explicit"
    assert resolve_agent_id(request=_Req()) == "from_state"
    assert resolve_agent_id(header="hdr") == "hdr"
    assert resolve_agent_id() == "default"


def test_create_and_list_and_isolation(tmp_path):
    from app.agents.multi_agent_manager import MultiAgentManager

    mgr = MultiAgentManager(root=tmp_path)
    a = mgr.create("agentA")
    b = mgr.create("agentB")
    assert a.root != b.root
    # write into A's files dir, ensure B cannot see it
    a.files_dir().mkdir(parents=True, exist_ok=True)
    (a.files_dir() / "report.md").write_text("hi", encoding="utf-8")
    b.files_dir().mkdir(parents=True, exist_ok=True)
    assert not (b.files_dir() / "report.md").exists()
    ids = {ws.agent_id for ws in mgr.list_agents()}
    assert {"agentA", "agentB"} <= ids


@pytest.mark.asyncio
async def test_default_not_deletable(tmp_path):
    from app.agents.multi_agent_manager import MultiAgentManager

    mgr = MultiAgentManager(root=tmp_path)
    mgr.create("default")
    with pytest.raises(ValueError):
        await mgr.delete("default")
    with pytest.raises(ValueError):
        await mgr.delete("default", purge=True)


@pytest.mark.asyncio
async def test_lazy_load_concurrent_single_build(tmp_path, monkeypatch):
    from app.agents import multi_agent_manager as mod
    from app.core import checkpoint as checkpoint_module
    from app.core.checkpoint import CheckpointProvider

    provider = CheckpointProvider("memory", tmp_path / "ck")
    await provider.initialize()
    monkeypatch.setattr(checkpoint_module, "checkpoint_provider", provider)

    mgr = mod.MultiAgentManager(root=tmp_path)
    build_count = {"n": 0}

    def fake_build(ws):
        build_count["n"] += 1
        return object()

    monkeypatch.setattr(mgr, "_build_agent", fake_build)

    results = await asyncio.gather(*[mgr.get_agent("shared") for _ in range(10)])
    assert build_count["n"] == 1
    assert all(r.agent is results[0].agent for r in results)
    await provider.close()
