"""Phase 4 tests: skill system (store, scanner, pool, workspace, registry)."""

import tempfile
from pathlib import Path


def _make_skill(base: Path, name: str, body: str = "hello") -> Path:
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: test skill {name}\nlanguages: zh, en\n---\n\n# {name}\n\n{body}\n",
        encoding="utf-8",
    )
    return d


def test_parse_frontmatter_and_manifest():
    from app.skills_system.store import read_skill_manifest

    with tempfile.TemporaryDirectory() as tmp:
        d = _make_skill(Path(tmp), "demo")
        info = read_skill_manifest(d)
        assert info is not None
        assert info.name == "demo"
        assert "zh" in info.languages


def test_scanner_detects_secret():
    from app.skills_system.scanner import skill_scanner

    with tempfile.TemporaryDirectory() as tmp:
        d = _make_skill(Path(tmp), "bad", body="api = 'sk-abcdef0123456789ABCD'")
        findings = skill_scanner.scan(d)
        assert len(findings) >= 1
        assert skill_scanner.is_safe(d) is False


def test_scanner_detects_dangerous_code():
    from app.skills_system.scanner import skill_scanner

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "danger"
        d.mkdir()
        (d / "SKILL.md").write_text("---\nname: danger\n---\n", encoding="utf-8")
        (d / "run.py").write_text("import os\nos.system('rm -rf /')\n", encoding="utf-8")
        findings = skill_scanner.scan(d)
        cats = {f.category for f in findings}
        assert "os_system" in cats


def test_builtin_pool_lists_skills():
    from app.skills_system.pool_service import skill_pool_service

    names = {s.name for s in skill_pool_service.list_skills()}
    # at least the built-in drilling skills should be discoverable
    assert "drilling-report" in names or len(names) >= 1


def test_resolve_effective_skills_fallback():
    from app.skills_system.registry import resolve_effective_skills

    dirs = resolve_effective_skills(workspace_dir=None, channel="console")
    assert isinstance(dirs, list)


def test_skill_governance_routes(monkeypatch):
    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.main import app

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        pool = root / "pool"
        agents = root / "agents"
        source = root / "source"
        pool.mkdir()
        agents.mkdir()
        skill_source = _make_skill(source, "demo")

        monkeypatch.setattr(settings, "skills_dir", pool, raising=False)
        monkeypatch.setattr(settings, "agents_root", agents, raising=False)

        client = TestClient(app)
        res = client.post("/api/v1/skills/install", json={"name": "demo", "source_dir": str(skill_source)})
        assert res.status_code == 200

        res = client.get("/api/v1/skills/pool/demo")
        assert res.status_code == 200
        assert res.json()["info"]["name"] == "demo"
        assert any(f["path"] == "SKILL.md" for f in res.json()["files"])

        res = client.put(
            "/api/v1/skills/pool/demo/file",
            json={
                "path": "SKILL.md",
                "content": "---\nname: demo\ndescription: updated\n---\n\n# demo\n",
            },
        )
        assert res.status_code == 200
        assert res.json()["info"]["description"] == "updated"

        res = client.get("/api/v1/skills/pool/demo/scan-report")
        assert res.status_code == 200
        assert res.json()["safe"] is True

        res = client.post("/api/v1/skills/demo/add-to-workspace?agent_id=a1")
        assert res.status_code == 200
        res = client.delete("/api/v1/skills/workspace/demo?agent_id=a1")
        assert res.status_code == 200

        res = client.delete("/api/v1/skills/pool/demo")
        assert res.status_code == 200


def test_skill_reload_rebuilds_loaded_agent(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.agents.multi_agent_manager import multi_agent_manager
    from app.agents.workspace import Workspace
    from app.main import app

    original_ws = dict(multi_agent_manager._ws)
    original_locks = dict(multi_agent_manager._locks)
    original_root = multi_agent_manager._root
    try:
        multi_agent_manager._root = tmp_path / "agents"
        multi_agent_manager._ws = {
            "loaded": Workspace(agent_id="loaded", root=multi_agent_manager._root / "loaded"),
            "idle": Workspace(agent_id="idle", root=multi_agent_manager._root / "idle"),
        }
        multi_agent_manager._ws["loaded"].agent = object()
        calls: list[str] = []

        def fake_build(ws):
            calls.append(ws.agent_id)
            return {"agent": ws.agent_id, "build": len(calls)}

        monkeypatch.setattr(multi_agent_manager, "_build_agent", fake_build)
        client = TestClient(app)

        res = client.post("/api/v1/skills/reload")
        assert res.status_code == 200
        assert res.json()["reloaded"] == 1
        assert calls == ["loaded"]
        assert multi_agent_manager._ws["loaded"].agent == {"agent": "loaded", "build": 1}
        assert multi_agent_manager._ws["idle"].agent is None

        res = client.post("/api/v1/skills/reload", json={"agent_id": "idle"})
        assert res.status_code == 200
        assert res.json()["reloaded"] == 0
        assert calls == ["loaded"]
        assert multi_agent_manager._ws["idle"].agent is None
    finally:
        multi_agent_manager._ws = original_ws
        multi_agent_manager._locks = original_locks
        multi_agent_manager._root = original_root
