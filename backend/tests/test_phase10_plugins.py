"""Phase 10 tests: plugin loader safe-default, command registry."""

import json


def _make_plugin(base, name, enabled_tool="echo_tool"):
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(
        json.dumps({"name": name, "plugin_type": "tool", "entry": "plugin.py"}), encoding="utf-8"
    )
    (d / "plugin.py").write_text(
        f'from langchain_core.tools import tool\n\n__all__ = ["{enabled_tool}"]\n\n\n@tool\ndef {enabled_tool}(text: str) -> str:\n    """echo"""\n    return text\n',
        encoding="utf-8",
    )
    return d


def test_plugin_disabled_not_loaded(tmp_path):
    from app.plugins.loader import discover_and_load
    from app.plugins.registry import plugin_registry

    _make_plugin(tmp_path, "p_disabled")
    infos = discover_and_load(plugins_dir=tmp_path, enabled=[])
    assert len(infos) == 1
    assert infos[0].enabled is False
    assert infos[0].loaded is False
    # safe default: no tools registered
    assert plugin_registry.enabled_tools() == []


def test_plugin_enabled_loads_tools(tmp_path):
    from app.plugins.loader import discover_and_load
    from app.plugins.registry import plugin_registry

    _make_plugin(tmp_path, "p_enabled")
    infos = discover_and_load(plugins_dir=tmp_path, enabled=["p_enabled"])
    assert infos[0].enabled is True and infos[0].loaded is True
    tool_names = {getattr(t, "name", "") for t in plugin_registry.enabled_tools()}
    assert "echo_tool" in tool_names


def test_command_new_switches_thread():
    from app.commands.registry import command_registry

    result = command_registry.execute("/new", {"thread_id": "old"})
    assert result is not None and result.handled
    assert result.new_thread_id and result.new_thread_id != "old"


def test_command_help_lists_commands():
    from app.commands.registry import command_registry

    result = command_registry.execute("/help")
    assert result is not None
    assert "/new" in result.response and "/clear" in result.response
    assert "可用命令" in result.response


def test_command_i18n_english_context():
    from app.commands.registry import command_registry

    result = command_registry.execute("/help", {"lang": "en-US"})
    assert result is not None
    assert "Available commands:" in result.response
    assert "/new - Start a new conversation thread" in result.response

    new_result = command_registry.execute("/new", {"lang": "en"})
    assert new_result is not None
    assert new_result.response == "Started a new conversation."


def test_chat_command_i18n_lang_override():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.post("/api/v1/agent/chat", json={"message": "/help", "lang": "en"})

    assert resp.status_code == 200
    assert "Available commands:" in resp.json()["response"]


def test_chat_command_i18n_accept_language_header():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.post("/api/v1/agent/chat", json={"message": "/help"}, headers={"Accept-Language": "en-US,en;q=0.9"})

    assert resp.status_code == 200
    assert "Available commands:" in resp.json()["response"]


def test_chat_command_i18n_body_lang_precedence():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    resp = client.post(
        "/api/v1/agent/chat",
        json={"message": "/help", "lang": "zh"},
        headers={"Accept-Language": "en-US,en;q=0.9"},
    )

    assert resp.status_code == 200
    assert "可用命令" in resp.json()["response"]


def test_command_plan_passes_through():
    from app.commands.registry import command_registry

    result = command_registry.execute("/plan 写日报")
    assert result is not None
    assert result.pass_through is True and result.handled is False


def test_command_unknown_returns_none():
    from app.commands.registry import command_registry

    assert command_registry.execute("普通消息") is None
    assert command_registry.execute("/notacommand") is None


def test_command_alias_reset():
    from app.commands.registry import command_registry

    result = command_registry.execute("/reset")
    assert result is not None and result.action == "clear"


def test_builtin_tools_have_no_plugin_tool():
    """Disabled example plugin's tool must not appear among agent tools by default."""
    from app.core.agent_factory import get_builtin_tools

    names = {t.name for t in get_builtin_tools()}
    assert "echo_tool" not in names


def test_plugin_governance_routes_install_enable_detail(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.api.routes import plugins as plugin_routes
    from app.core.config import settings
    from app.main import app
    from app.plugins.registry import plugin_registry

    plugins_dir = tmp_path / "plugins"
    source_dir = tmp_path / "source"
    env_path = tmp_path / ".env"
    plugins_dir.mkdir()
    env_path.write_text("ENABLED_PLUGINS=\n", encoding="utf-8")
    _make_plugin(source_dir, "p_demo")

    monkeypatch.setattr(plugin_routes, "PLUGIN_ENV_PATH", env_path, raising=False)
    monkeypatch.setattr(settings, "plugins_dir", plugins_dir, raising=False)
    monkeypatch.setattr(settings, "enabled_plugins", "", raising=False)
    plugin_registry.clear()

    client = TestClient(app)
    res = client.post("/api/v1/plugins/install", json={"name": "p_demo", "source_dir": str(source_dir / "p_demo")})
    assert res.status_code == 200
    assert res.json()["enabled"] is False

    res = client.get("/api/v1/plugins/p_demo")
    assert res.status_code == 200
    assert res.json()["manifest"]["name"] == "p_demo"

    res = client.put("/api/v1/plugins/p_demo/enabled", json={"enabled": True})
    assert res.status_code == 200
    assert res.json()["enabled"] is True
    assert res.json()["loaded"] is True
    assert "p_demo" in settings.enabled_plugins
    assert "ENABLED_PLUGINS=p_demo" in env_path.read_text(encoding="utf-8")

    res = client.put("/api/v1/plugins/p_demo/enabled", json={"enabled": False})
    assert res.status_code == 200
    assert res.json()["enabled"] is False
    assert "p_demo" not in settings.enabled_plugins
    assert "ENABLED_PLUGINS=\"\"" in env_path.read_text(encoding="utf-8")


def test_plugin_governance_routes_isolate_load_error(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.api.routes import plugins as plugin_routes
    from app.core.config import settings
    from app.main import app
    from app.plugins.registry import plugin_registry

    plugins_dir = tmp_path / "plugins"
    env_path = tmp_path / ".env"
    bad = plugins_dir / "bad_plugin"
    bad.mkdir(parents=True)
    env_path.write_text("ENABLED_PLUGINS=\n", encoding="utf-8")
    (bad / "manifest.json").write_text(
        json.dumps({"name": "bad_plugin", "plugin_type": "tool", "entry": "plugin.py"}),
        encoding="utf-8",
    )
    (bad / "plugin.py").write_text("raise RuntimeError('boom')\n", encoding="utf-8")

    monkeypatch.setattr(plugin_routes, "PLUGIN_ENV_PATH", env_path, raising=False)
    monkeypatch.setattr(settings, "plugins_dir", plugins_dir, raising=False)
    monkeypatch.setattr(settings, "enabled_plugins", "", raising=False)
    plugin_registry.clear()

    client = TestClient(app)
    res = client.put("/api/v1/plugins/bad_plugin/enabled", json={"enabled": True})
    assert res.status_code == 200
    assert res.json()["enabled"] is True
    assert res.json()["loaded"] is False
    assert "boom" in res.json()["error"]
    assert "ENABLED_PLUGINS=bad_plugin" in env_path.read_text(encoding="utf-8")
