"""Tests for Agent Configuration Studio: profile persistence, validation, concurrency and rollback."""

from __future__ import annotations

import asyncio
import json

import pytest


@pytest.fixture
def profile_env(tmp_path, monkeypatch):
    from app.agents import multi_agent_manager as mam_mod
    from app.agents.profile.service import AgentProfileService
    from app.agents.profile.store import ProfileStore
    from app.agents.profile.versions import VersionRepository

    agents_root = tmp_path / "agents"
    agents_root.mkdir()
    monkeypatch.setattr(mam_mod.multi_agent_manager, "_root", agents_root)
    monkeypatch.setattr(mam_mod.multi_agent_manager, "_ws", {})
    store = ProfileStore(agents_root)
    service = AgentProfileService(store=store, versions=VersionRepository(agents_root))
    monkeypatch.setattr("app.agents.profile.service.profile_service", service)
    return {"root": agents_root, "service": service, "manager": mam_mod.multi_agent_manager}


def test_profile_persists_after_restart(profile_env):
    service = profile_env["service"]
    manager = profile_env["manager"]

    manager.create("analyst")
    profile = service.get_or_create("analyst")
    response = asyncio.run(
        service.apply_profile(
            "analyst",
            {"display_name": "分析助手", "system_prompt": "专注数据分析", "provider": "", "model": ""},
            expected_revision=profile.revision,
        )
    )
    assert response.configured["display_name"] == "分析助手"
    path = profile_env["root"] / "analyst" / "agent.json"
    assert path.exists()
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert reloaded["display_name"] == "分析助手"
    assert reloaded["revision"] == 2


def test_revision_conflict_returns_error(profile_env):
    service = profile_env["service"]
    manager = profile_env["manager"]
    manager.create("ops")
    current = service.get_or_create("ops")
    asyncio.run(
        service.apply_profile(
            "ops",
            {"display_name": "A"},
            expected_revision=current.revision,
        )
    )
    stale_revision = current.revision
    from app.agents.profile.store import ProfileConflictError

    with pytest.raises(ProfileConflictError) as exc:
        asyncio.run(
            service.apply_profile(
                "ops",
                {"display_name": "B"},
                expected_revision=stale_revision,
            )
        )
    assert exc.value.actual_revision == 2


def test_validate_only_does_not_persist(profile_env):
    service = profile_env["service"]
    manager = profile_env["manager"]
    manager.create("validate-me")
    before = service.get_or_create("validate-me")
    result = service.validate_payload("validate-me", {"display_name": "校验名称"})
    assert result.valid is True
    after = service.get_or_create("validate-me")
    assert after.revision == before.revision
    assert after.display_name != "校验名称"


def test_rejects_invalid_model_and_secrets(profile_env):
    service = profile_env["service"]
    manager = profile_env["manager"]
    manager.create("secure")
    result = service.validate_payload(
        "secure",
        {"provider": "openai", "model": "definitely-not-a-real-model-name-xyz"},
    )
    assert result.valid is False

    secret_result = service.validate_payload(
        "secure",
        {"system_prompt": "use api_key=sk-test12345678901234567890123456789012"},
    )
    assert secret_result.valid is False


@pytest.mark.asyncio
async def test_clone_does_not_copy_sessions_or_files(profile_env, tmp_path):
    service = profile_env["service"]
    manager = profile_env["manager"]
    manager.create("source")
    source_root = profile_env["root"] / "source"
    (source_root / "files").mkdir(parents=True)
    (source_root / "files" / "secret.txt").write_text("data", encoding="utf-8")

    current = service.get_or_create("source")
    await service.apply_profile(
        "source",
        {"display_name": "源 Agent", "description": "可复制"},
        expected_revision=current.revision,
    )
    cloned = await service.clone_agent("source", new_agent_id="source-copy", copy_skills=False)
    assert cloned.agent_id == "source-copy"
    assert not (profile_env["root"] / "source-copy" / "files" / "secret.txt").exists()


@pytest.mark.asyncio
async def test_rollback_creates_new_revision(profile_env):
    service = profile_env["service"]
    manager = profile_env["manager"]
    manager.create("rollback-agent")
    rev1 = service.get_or_create("rollback-agent")
    await service.apply_profile(
        "rollback-agent",
        {"display_name": "版本一"},
        expected_revision=rev1.revision,
    )
    rev2 = service.get_or_create("rollback-agent")
    await service.apply_profile(
        "rollback-agent",
        {"display_name": "版本二"},
        expected_revision=rev2.revision,
    )
    rolled = await service.rollback("rollback-agent", 2)
    assert rolled.revision == 4
    assert rolled.configured["display_name"] == "版本一"


def test_export_import_roundtrip(profile_env):
    service = profile_env["service"]
    manager = profile_env["manager"]
    manager.create("portable")
    current = service.get_or_create("portable")
    asyncio.run(
        service.apply_profile(
            "portable",
            {"display_name": "可移植", "tool_policy": "safe_only"},
            expected_revision=current.revision,
        )
    )
    exported = service.export_profile("portable")
    assert "api_key" not in json.dumps(exported)
    imported = asyncio.run(service.import_profile(exported, agent_id="portable-imported"))
    assert imported.configured["display_name"] == "可移植"
    assert imported.agent_id == "portable-imported"
