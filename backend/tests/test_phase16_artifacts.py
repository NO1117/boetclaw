"""Phase 16.4 tests: artifact center API."""

import hashlib
import json


def test_artifact_listing_and_download(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.main import app

    charts = tmp_path / "charts"
    code = tmp_path / "code"
    charts.mkdir()
    code.mkdir()
    (charts / "chart_demo.png").write_bytes(b"png")
    (code / "code_demo.py").write_text("print('hello')\n", encoding="utf-8")

    monkeypatch.setattr(settings, "workspace_dir", tmp_path, raising=False)
    client = TestClient(app)

    res = client.get("/api/v1/files/artifacts")
    assert res.status_code == 200
    rows = res.json()["artifacts"]
    assert {r["kind"] for r in rows} == {"chart", "code"}
    code_row = next(r for r in rows if r["kind"] == "code")
    assert code_row["preview"].startswith("print")
    assert code_row["sha256"] == hashlib.sha256((code / "code_demo.py").read_bytes()).hexdigest()

    res = client.get("/api/v1/files/artifacts/code/code_demo.py/download")
    assert res.status_code == 200
    assert b"print" in res.content


def test_artifact_download_rejects_unsafe_path(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.main import app

    (tmp_path / "code").mkdir()
    monkeypatch.setattr(settings, "workspace_dir", tmp_path, raising=False)
    client = TestClient(app)

    res = client.get("/api/v1/files/artifacts/code/..%2Fsecret.txt/download")
    assert res.status_code in (400, 404)


def test_artifact_delete_removes_file_and_metadata(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.main import app

    charts = tmp_path / "charts"
    artifacts = tmp_path / "artifacts"
    charts.mkdir()
    artifacts.mkdir()
    (charts / "chart_demo.png").write_bytes(b"png")
    meta_path = artifacts / "chart_chart_demo.png.json"
    meta_path.write_text(json.dumps({"trace_id": "trace-1"}), encoding="utf-8")

    monkeypatch.setattr(settings, "workspace_dir", tmp_path, raising=False)
    client = TestClient(app)

    res = client.delete("/api/v1/files/artifacts/chart/chart_demo.png")
    assert res.status_code == 200
    assert res.json() == {"deleted": "chart_demo.png", "kind": "chart"}
    assert not (charts / "chart_demo.png").exists()
    assert not meta_path.exists()

    res = client.delete("/api/v1/files/artifacts/chart/chart_demo.png")
    assert res.status_code == 404
