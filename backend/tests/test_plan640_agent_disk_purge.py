"""PLAN-640: Agent disk discovery, tombstone listing, and purge cleanup."""

from __future__ import annotations

import pytest


def test_list_agents_discovers_disk_and_skips_tombstone(tmp_path):
    from app.agents.multi_agent_manager import MultiAgentManager

    root = tmp_path / "agents"
    disk_agent = root / "from-disk"
    disk_agent.mkdir(parents=True)
    (disk_agent / "skills").mkdir()
    (disk_agent / "files").mkdir()

    tomb = root / "gone"
    tomb.mkdir(parents=True)
    (tomb / ".deleted").write_text("deleted\n", encoding="utf-8")

    # Cold start: empty memory, only disk state.
    mgr = MultiAgentManager(root=root)
    ids = {ws.agent_id for ws in mgr.list_agents()}
    assert "from-disk" in ids
    assert "gone" not in ids
    assert "default" in ids
    # Lazy metadata only — graph not built.
    assert mgr.get_workspace("from-disk") is not None
    assert mgr.get_workspace("from-disk").agent is None


@pytest.mark.asyncio
async def test_tombstone_hides_from_list_and_blocks_registration(tmp_path):
    from app.agents.multi_agent_manager import MultiAgentManager

    mgr = MultiAgentManager(root=tmp_path)
    mgr.create("soft")
    assert await mgr.delete("soft", purge=False)
    assert (tmp_path / "soft" / ".deleted").exists()
    assert (tmp_path / "soft").is_dir()
    ids = {ws.agent_id for ws in mgr.list_agents()}
    assert "soft" not in ids
    assert not mgr.is_registered("soft")
    assert mgr.get_workspace("soft") is None


@pytest.mark.asyncio
async def test_purge_removes_workspace_and_checkpoint(tmp_path, monkeypatch):
    from app.agents.multi_agent_manager import MultiAgentManager
    from app.core import checkpoint as checkpoint_module
    from app.core.checkpoint import CheckpointProvider

    agents_root = tmp_path / "agents"
    ckpt_root = tmp_path / "checkpoints"
    provider = CheckpointProvider("sqlite", ckpt_root)
    await provider.initialize()
    monkeypatch.setattr(checkpoint_module, "checkpoint_provider", provider)

    mgr = MultiAgentManager(root=agents_root)
    mgr.create("to-purge")
    await provider.get("to-purge")
    db = provider.database_path("to-purge")
    assert db.exists()

    assert await mgr.delete("to-purge", purge=True)
    assert not (agents_root / "to-purge").exists()
    assert not db.exists()
    assert "to-purge" not in {ws.agent_id for ws in mgr.list_agents()}
    assert not mgr.is_registered("to-purge")

    await provider.close()


@pytest.mark.asyncio
async def test_default_reject_delete_and_purge(tmp_path):
    from app.agents.multi_agent_manager import MultiAgentManager
    from app.core.checkpoint import CheckpointProvider

    mgr = MultiAgentManager(root=tmp_path)
    mgr.create("default")
    with pytest.raises(ValueError, match="不可删除"):
        await mgr.delete("default")
    with pytest.raises(ValueError, match="不可删除"):
        await mgr.delete("default", purge=True)

    provider = CheckpointProvider("sqlite", tmp_path / "ck")
    await provider.initialize()
    with pytest.raises(ValueError, match="不可清除"):
        await provider.purge("default")
    await provider.close()


@pytest.mark.asyncio
async def test_api_delete_purge_query_and_body(tmp_path, monkeypatch):
    from fastapi import HTTPException

    from app.agents import multi_agent_manager as mam
    from app.api.routes import agents as agents_routes
    from app.core import checkpoint as checkpoint_module
    from app.core.checkpoint import CheckpointProvider

    agents_root = tmp_path / "agents"
    ckpt_root = tmp_path / "checkpoints"
    provider = CheckpointProvider("sqlite", ckpt_root)
    await provider.initialize()

    mgr = mam.MultiAgentManager(root=agents_root)
    monkeypatch.setattr(mam, "multi_agent_manager", mgr)
    monkeypatch.setattr(agents_routes, "multi_agent_manager", mgr)
    monkeypatch.setattr(checkpoint_module, "checkpoint_provider", provider)

    try:
        mgr.create("a-tomb")
        mgr.create("a-purge")
        await provider.get("a-purge")

        soft = await agents_routes.delete_agent("a-tomb", request=None, purge=False, body=None)
        assert soft["purged"] is False
        assert soft["checkpoint_retained"] is True
        assert (agents_root / "a-tomb" / ".deleted").exists()

        listed = await agents_routes.list_agents(request=None)
        ids = {a["agent_id"] for a in listed["agents"]}
        assert "a-tomb" not in ids
        assert "a-purge" in ids
        assert "default" in ids

        with pytest.raises(HTTPException) as default_exc:
            await agents_routes.delete_agent("default", request=None, purge=True, body=None)
        assert default_exc.value.status_code == 400

        hard = await agents_routes.delete_agent("a-purge", request=None, purge=True, body=None)
        assert hard["purged"] is True
        assert hard["checkpoint_retained"] is False
        assert not (agents_root / "a-purge").exists()
        assert not provider.database_path("a-purge").exists()
        assert mgr.was_purged("a-purge")

        mgr.create("body-purge")
        via_body = await agents_routes.delete_agent(
            "body-purge",
            request=None,
            purge=False,
            body=agents_routes.DeleteAgentBody(purge=True),
        )
        assert via_body["purged"] is True
        assert not (agents_root / "body-purge").exists()
    finally:
        await provider.close()


@pytest.mark.asyncio
async def test_resume_after_purge_returns_409(tmp_path, monkeypatch):
    from app.agents.multi_agent_manager import MultiAgentManager
    from app.core import checkpoint as checkpoint_module
    from app.core.checkpoint import CheckpointProvider
    from app.core.execution_ref import ExecutionRef
    from app.services.execution_resume import ResumeValidationError, resolve_agent_for_resume

    agents_root = tmp_path / "agents"
    provider = CheckpointProvider("sqlite", tmp_path / "checkpoints")
    await provider.initialize()
    monkeypatch.setattr(checkpoint_module, "checkpoint_provider", provider)

    mgr = MultiAgentManager(root=agents_root)
    monkeypatch.setattr(
        "app.agents.multi_agent_manager.multi_agent_manager",
        mgr,
    )

    mgr.create("purged-resume")
    await provider.get("purged-resume")
    assert await mgr.delete("purged-resume", purge=True)

    ref = ExecutionRef(
        agent_id="purged-resume",
        thread_id="t1",
        checkpoint_ns="",
        interrupt_id="i1",
        interrupt_type="plan_confirm",
    )
    with pytest.raises(ResumeValidationError) as exc_info:
        await resolve_agent_for_resume(ref)
    assert exc_info.value.status_code == 409

    await provider.close()


@pytest.mark.asyncio
async def test_api_cold_start_lists_disk_agent(tmp_path, monkeypatch):
    from app.agents import multi_agent_manager as mam
    from app.api.routes import agents as agents_routes

    agents_root = tmp_path / "agents"
    disk = agents_root / "cold-disk"
    disk.mkdir(parents=True)
    (disk / "files").mkdir()

    mgr = mam.MultiAgentManager(root=agents_root)
    monkeypatch.setattr(mam, "multi_agent_manager", mgr)
    monkeypatch.setattr(agents_routes, "multi_agent_manager", mgr)

    listed = await agents_routes.list_agents(request=None)
    ids = {a["agent_id"] for a in listed["agents"]}
    assert "cold-disk" in ids
    assert "default" in ids
    detail = await agents_routes.get_agent("cold-disk", request=None)
    assert detail["loaded"] is False
