"""Artifact sidecar metadata tests."""

import json


def test_generated_code_writes_sidecar_metadata(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.core.observability import run_id_var, trace_id_var
    from app.core.run_context import reset_run_context, set_run_context
    from app.main import app
    from app.tools.builtin import generate_code

    monkeypatch.setattr(settings, "workspace_dir", tmp_path, raising=False)
    trace_id_var.set("trace-meta")
    run_id_var.set("run-meta")
    tokens = set_run_context(task_id="task-meta", agent_id="agent-meta", well_id="well-meta")
    try:
        result = json.loads(
            generate_code.invoke(
                {
                    "description": "生成测试脚本",
                    "language": "python",
                    "framework": "",
                }
            )
        )
    finally:
        reset_run_context(tokens)

    filename = result["file_path"].split("\\")[-1].split("/")[-1]
    meta_path = tmp_path / "artifacts" / f"code_{filename}.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["task_id"] == "task-meta"
    assert meta["trace_id"] == "trace-meta"
    assert meta["run_id"] == "run-meta"
    assert meta["agent_id"] == "agent-meta"
    assert meta["well_id"] == "well-meta"

    client = TestClient(app)
    res = client.get("/api/v1/files/artifacts?kind=code")
    assert res.status_code == 200
    artifact = res.json()["artifacts"][0]
    assert artifact["task_id"] == "task-meta"
    assert artifact["trace_id"] == "trace-meta"
    assert artifact["agent_id"] == "agent-meta"
    assert artifact["well_id"] == "well-meta"

    res = client.get("/api/v1/files/artifacts?kind=code&agent_id=agent-meta")
    assert res.status_code == 200
    assert len(res.json()["artifacts"]) == 1

    res = client.get("/api/v1/files/artifacts?kind=code&agent_id=other-agent")
    assert res.status_code == 200
    assert res.json()["artifacts"] == []
