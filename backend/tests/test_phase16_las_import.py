"""Phase 16.5 tests: LAS import and quality checks."""

import json


LAS_TEXT = """~Version
VERS. 2.0
~Curve
DEPT.M : Depth
GR.API : Gamma Ray
RT.OHMM : Resistivity
~A
1000 80 12
1001 -999.25 13
"""


def test_parse_las_text_quality():
    from app.domain.las_importer import parse_las_text

    parsed = parse_las_text(LAS_TEXT)
    assert parsed["curves"] == ["DEPT", "GR", "RT"]
    assert parsed["quality"]["point_count"] == 2
    assert parsed["quality"]["null_count"] == 1
    assert parsed["quality"]["depth_min"] == 1000
    assert parsed["quality"]["depth_max"] == 1001


def test_las_import_route_persists_curve_data(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.domain.store import domain_store
    from app.main import app

    las = tmp_path / "xx-1.las"
    las.write_text(LAS_TEXT, encoding="utf-8")
    monkeypatch.setattr(settings, "workspace_dir", tmp_path, raising=False)
    monkeypatch.setattr(domain_store, "path", tmp_path / "domain.json", raising=False)

    client = TestClient(app)
    well = client.post("/api/v1/domain/wells", json={"name": "XX-1"}).json()
    res = client.post("/api/v1/domain/las/import", json={"well_id": well["id"], "path": str(las)})

    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "imported"
    assert body["curves"] == ["DEPT", "GR", "RT"]
    assert body["quality"]["null_count"] == 1
    curve_rows = json.loads((tmp_path / "domain" / "las_curves" / f"{body['id']}.json").read_text(encoding="utf-8"))
    assert len(curve_rows) == 2


def test_las_upload_route_persists_uploaded_file_and_curve_data(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.domain.store import domain_store
    from app.main import app

    monkeypatch.setattr(settings, "workspace_dir", tmp_path, raising=False)
    monkeypatch.setattr(domain_store, "path", tmp_path / "domain.json", raising=False)

    client = TestClient(app)
    well = client.post("/api/v1/domain/wells", json={"name": "XX-1"}).json()
    res = client.post(
        "/api/v1/domain/las/upload",
        data={"well_id": well["id"], "filename": "uploaded.las"},
        files={"file": ("ignored-name.las", LAS_TEXT.encode("utf-8"), "text/plain")},
    )

    assert res.status_code == 200
    body = res.json()
    assert body["filename"] == "uploaded.las"
    assert body["status"] == "imported"
    assert body["quality"]["point_count"] == 2
    assert (tmp_path / "domain" / "las_uploads" / "uploaded.las").exists()
    curve_rows = json.loads((tmp_path / "domain" / "las_curves" / f"{body['id']}.json").read_text(encoding="utf-8"))
    assert curve_rows[1]["GR"] is None


def test_las_upload_rejects_extension_size_and_content(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.domain.store import domain_store
    from app.main import app

    monkeypatch.setattr(settings, "workspace_dir", tmp_path, raising=False)
    monkeypatch.setattr(settings, "las_upload_max_bytes", 8, raising=False)
    monkeypatch.setattr(domain_store, "path", tmp_path / "domain.json", raising=False)

    client = TestClient(app)
    well = client.post("/api/v1/domain/wells", json={"name": "XX-1"}).json()

    bad_extension = client.post(
        "/api/v1/domain/las/upload",
        data={"well_id": well["id"], "filename": "not-las.txt"},
        files={"file": ("not-las.txt", LAS_TEXT.encode("utf-8"), "text/plain")},
    )
    assert bad_extension.status_code == 400
    assert bad_extension.json()["detail"]["code"] == "invalid_las_extension"

    too_large = client.post(
        "/api/v1/domain/las/upload",
        data={"well_id": well["id"], "filename": "too-large.las"},
        files={"file": ("too-large.las", LAS_TEXT.encode("utf-8"), "text/plain")},
    )
    assert too_large.status_code == 413
    assert too_large.json()["detail"]["code"] == "las_upload_too_large"

    monkeypatch.setattr(settings, "las_upload_max_bytes", 1024, raising=False)
    invalid_content = client.post(
        "/api/v1/domain/las/upload",
        data={"well_id": well["id"], "filename": "invalid.las"},
        files={"file": ("invalid.las", b"plain text", "text/plain")},
    )
    assert invalid_content.status_code == 400
    assert invalid_content.json()["detail"]["code"] == "invalid_las_content"

    assert domain_store.list("las_files") == []
    assert not (tmp_path / "domain" / "las_uploads").exists()
