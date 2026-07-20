"""Phase 15.3 tests: MCP management API."""

import pytest


class _FakeTool:
    name = "demo_mcp_tool"
    description = "demo tool"
    args_schema = None


def test_mcp_management_routes(monkeypatch):
    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.main import app
    from app.tools.mcp_manager import mcp_manager

    monkeypatch.setattr(settings, "mcp_servers", '{"demo":{"command":"demo-mcp"}}', raising=False)
    monkeypatch.setattr(mcp_manager, "_servers", {"demo": {"command": "demo-mcp"}}, raising=False)
    monkeypatch.setattr(mcp_manager, "_tools", [_FakeTool()], raising=False)

    client = TestClient(app)

    res = client.get("/api/v1/tools/mcp/servers")
    assert res.status_code == 200
    assert res.json()["servers"][0]["name"] == "demo"
    assert res.json()["servers"][0]["connected"] is True

    res = client.get("/api/v1/tools/mcp/tools")
    assert res.status_code == 200
    assert res.json()["tools"][0]["name"] == "demo_mcp_tool"

    res = client.get("/api/v1/tools/mcp/tools/demo_mcp_tool")
    assert res.status_code == 200
    assert res.json()["description"] == "demo tool"


@pytest.mark.asyncio
async def test_mcp_reload_records_recover_counts(monkeypatch):
    from app.tools.mcp_manager import mcp_manager

    async def ok_disconnect():
        return None

    async def ok_connect():
        return True

    async def unavailable_connect():
        return False

    async def failed_connect():
        raise RuntimeError("mcp down")

    monkeypatch.setattr(mcp_manager, "_recover_counts", {"success": 0, "failed": 0}, raising=False)
    monkeypatch.setattr(mcp_manager, "disconnect", ok_disconnect)
    monkeypatch.setattr(mcp_manager, "connect", ok_connect)

    await mcp_manager.reload()
    assert mcp_manager.recover_counts() == {"success": 1, "failed": 0}

    monkeypatch.setattr(mcp_manager, "connect", unavailable_connect)
    await mcp_manager.reload()
    assert mcp_manager.recover_counts() == {"success": 1, "failed": 1}

    monkeypatch.setattr(mcp_manager, "connect", failed_connect)
    try:
        await mcp_manager.reload()
    except RuntimeError as exc:
        assert str(exc) == "mcp down"
    else:
        raise AssertionError("reload should propagate MCP reconnect errors")

    assert mcp_manager.recover_counts() == {"success": 1, "failed": 2}
