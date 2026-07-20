"""PLAN-630: plugin security scan gate and delete governance."""

from __future__ import annotations

import json


def _make_plugin(base, name, *, plugin_body: str | None = None):
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(
        json.dumps({"name": name, "plugin_type": "tool", "entry": "plugin.py"}),
        encoding="utf-8",
    )
    body = plugin_body or (
        'from langchain_core.tools import tool\n\n'
        '__all__ = ["echo_tool"]\n\n\n'
        '@tool\ndef echo_tool(text: str) -> str:\n'
        '    """echo"""\n'
        '    return text\n'
    )
    (d / "plugin.py").write_text(body, encoding="utf-8")
    return d


def _setup_client(monkeypatch, tmp_path, *, enabled: str = ""):
    from fastapi.testclient import TestClient

    from app.api.routes import plugins as plugin_routes
    from app.core.config import settings
    from app.main import app
    from app.plugins.registry import plugin_registry

    plugins_dir = tmp_path / "plugins"
    env_path = tmp_path / ".env"
    plugins_dir.mkdir()
    env_path.write_text(f"ENABLED_PLUGINS={enabled}\n", encoding="utf-8")

    monkeypatch.setattr(plugin_routes, "PLUGIN_ENV_PATH", env_path, raising=False)
    monkeypatch.setattr(settings, "plugins_dir", plugins_dir, raising=False)
    monkeypatch.setattr(settings, "enabled_plugins", enabled, raising=False)
    plugin_registry.clear()

    return TestClient(app), plugins_dir, env_path


def test_safe_plugin_install_stays_disabled(monkeypatch, tmp_path):
    client, plugins_dir, env_path = _setup_client(monkeypatch, tmp_path)
    source = _make_plugin(tmp_path / "source", "safe_plugin")

    res = client.post(
        "/api/v1/plugins/install",
        json={"name": "safe_plugin", "source_dir": str(source)},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["name"] == "safe_plugin"
    assert body["enabled"] is False
    assert (plugins_dir / "safe_plugin").exists()
    assert "safe_plugin" not in env_path.read_text(encoding="utf-8")


def test_dangerous_plugin_install_rejected(monkeypatch, tmp_path):
    client, plugins_dir, _env_path = _setup_client(monkeypatch, tmp_path)
    source = _make_plugin(
        tmp_path / "source",
        "danger_plugin",
        plugin_body='import os\nos.system("echo pwned")\n',
    )

    res = client.post(
        "/api/v1/plugins/install",
        json={"name": "danger_plugin", "source_dir": str(source)},
    )
    assert res.status_code == 400
    detail = res.json()["detail"]
    assert detail["safe"] is False
    assert any(f["category"] == "os_system" for f in detail["findings"])
    assert not (plugins_dir / "danger_plugin").exists()


def test_plugin_scan_report_and_path_scan(monkeypatch, tmp_path):
    client, plugins_dir, _env_path = _setup_client(monkeypatch, tmp_path)
    installed = _make_plugin(plugins_dir, "report_plugin")

    res = client.get("/api/v1/plugins/report_plugin/scan-report")
    assert res.status_code == 200
    assert res.json()["safe"] is True

    dangerous = tmp_path / "loose"
    dangerous.mkdir()
    (dangerous / "x.py").write_text("eval('1')\n", encoding="utf-8")
    res = client.post("/api/v1/plugins/scan", json={"path": str(dangerous)})
    assert res.status_code == 200
    assert res.json()["safe"] is False
    assert any(f["category"] == "eval" for f in res.json()["findings"])

    # detail includes scan payload
    from app.plugins.loader import discover_and_load

    discover_and_load(plugins_dir=plugins_dir, enabled=[])
    res = client.get("/api/v1/plugins/report_plugin")
    assert res.status_code == 200
    assert res.json()["scan"]["safe"] is True
    assert installed.exists()


def test_plugin_delete_cleans_dir_and_enabled(monkeypatch, tmp_path):
    client, plugins_dir, env_path = _setup_client(monkeypatch, tmp_path, enabled="to_delete")
    _make_plugin(plugins_dir, "to_delete")

    from app.plugins.loader import reload_plugins

    reload_plugins()

    res = client.delete("/api/v1/plugins/to_delete")
    assert res.status_code == 200
    assert res.json()["deleted"] == "to_delete"
    assert not (plugins_dir / "to_delete").exists()
    assert "to_delete" not in env_path.read_text(encoding="utf-8")

    from app.core.config import settings
    from app.plugins.registry import plugin_registry

    assert "to_delete" not in settings.enabled_plugins
    assert plugin_registry.get("to_delete") is None


def test_plugin_delete_missing_404(monkeypatch, tmp_path):
    client, _plugins_dir, _env_path = _setup_client(monkeypatch, tmp_path)
    res = client.delete("/api/v1/plugins/missing_plugin")
    assert res.status_code == 404


def test_plugin_path_traversal_rejected(monkeypatch, tmp_path):
    from fastapi import HTTPException

    from app.api.routes import plugins as plugin_routes
    from app.core.config import settings

    client, plugins_dir, _env_path = _setup_client(monkeypatch, tmp_path)
    outside = tmp_path / "outside_secret"
    outside.mkdir()
    (outside / "keep.txt").write_text("keep", encoding="utf-8")

    # helper rejects ".", "..", separators, and resolved escapes
    for name in (".", "..", "../outside_secret", "a/b", "a\\b"):
        try:
            plugin_routes._safe_plugin_dir(name)
            raise AssertionError(f"expected unsafe: {name}")
        except HTTPException as exc:
            assert exc.status_code == 400

    # HTTP: encoded ".." reaches the handler as ".." and is rejected
    res = client.delete("/api/v1/plugins/%2e%2e")
    assert res.status_code == 400
    res = client.get("/api/v1/plugins/%2e%2e/scan-report")
    assert res.status_code == 400

    # literal ".." is normalized by the client/router away from /plugins/{name}
    res = client.delete("/api/v1/plugins/..")
    assert res.status_code == 404

    assert outside.exists()
    assert (outside / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert plugins_dir.exists()
    assert settings.plugins_dir == plugins_dir
