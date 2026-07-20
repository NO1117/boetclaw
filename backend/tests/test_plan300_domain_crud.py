"""PLAN-300 domain CRUD, relation, and JSON durability tests."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def domain_client(monkeypatch, tmp_path):
    from app.core.config import settings
    from app.domain.store import domain_store
    from app.main import app

    monkeypatch.setattr(settings, "workspace_dir", tmp_path, raising=False)
    monkeypatch.setattr(domain_store, "path", tmp_path / "domain.json", raising=False)
    return TestClient(app), tmp_path


def _create_well(client: TestClient, name: str = "PLAN-300") -> dict:
    response = client.post("/api/v1/domain/wells", json={"name": name})
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize(
    ("path", "payload", "changes"),
    [
        (
            "sections",
            {"name": "12-1/4", "top_depth": 0, "bottom_depth": 1200},
            {"name": "8-1/2", "top_depth": 1200, "bottom_depth": 2400},
        ),
        (
            "reports",
            {"report_date": "2026-07-16", "summary": "drilling"},
            {"report_date": "2026-07-17", "summary": "updated"},
        ),
        (
            "params",
            {"measured_depth": 1000, "wob": 10},
            {"measured_depth": 1100, "wob": 12},
        ),
        (
            "las-files",
            {"filename": "registered.las", "curves": ["GR"]},
            {"filename": "updated.las", "curves": ["GR", "RT"]},
        ),
    ],
)
def test_related_entities_full_crud_and_missing_errors(domain_client, path, payload, changes):
    client, _ = domain_client
    well = _create_well(client)
    created = client.post(f"/api/v1/domain/{path}", json={"well_id": well["id"], **payload})
    assert created.status_code == 200
    item_id = created.json()["id"]

    assert client.get(f"/api/v1/domain/{path}/{item_id}").status_code == 200
    listed = client.get(f"/api/v1/domain/{path}?well_id={well['id']}")
    assert [item["id"] for item in listed.json()] == [item_id]

    updated = client.put(f"/api/v1/domain/{path}/{item_id}", json={"well_id": well["id"], **changes})
    assert updated.status_code == 200
    assert updated.json()["updated_at"] != ""

    missing_well = client.put(f"/api/v1/domain/{path}/{item_id}", json={"well_id": "missing", **changes})
    assert missing_well.status_code == 404
    assert missing_well.json()["detail"]["code"] == "well_not_found"
    assert client.get(f"/api/v1/domain/{path}/{item_id}").json()["well_id"] == well["id"]

    deleted = client.delete(f"/api/v1/domain/{path}/{item_id}")
    assert deleted.status_code == 200
    assert client.get(f"/api/v1/domain/{path}/{item_id}").status_code == 404
    assert client.delete(f"/api/v1/domain/{path}/{item_id}").status_code == 404


def test_related_create_rejects_missing_well(domain_client):
    client, _ = domain_client
    response = client.post(
        "/api/v1/domain/reports",
        json={"well_id": "missing", "report_date": "2026-07-16"},
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "well_not_found"


def test_well_delete_conflict_lists_domain_and_artifact_dependencies(domain_client):
    client, workspace = domain_client
    well = _create_well(client)
    report = client.post(
        "/api/v1/domain/reports",
        json={"well_id": well["id"], "report_date": "2026-07-16"},
    ).json()
    artifact_dir = workspace / "artifacts"
    artifact_dir.mkdir()
    (artifact_dir / "code_output.py.json").write_text(
        json.dumps({"well_id": well["id"]}),
        encoding="utf-8",
    )

    response = client.delete(f"/api/v1/domain/wells/{well['id']}")
    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "well_has_dependencies"
    assert detail["dependencies"] == {"reports": 1, "artifacts": 1}
    assert client.get(f"/api/v1/domain/wells/{well['id']}").status_code == 200

    assert client.delete(f"/api/v1/domain/reports/{report['id']}").status_code == 200
    (artifact_dir / "code_output.py.json").unlink()
    assert client.delete(f"/api/v1/domain/wells/{well['id']}").status_code == 200
    assert client.delete(f"/api/v1/domain/wells/{well['id']}").status_code == 404


def test_las_delete_removes_only_managed_files(domain_client):
    client, workspace = domain_client
    well = _create_well(client)
    upload_dir = workspace / "domain" / "las_uploads"
    curve_dir = workspace / "domain" / "las_curves"
    upload_dir.mkdir(parents=True)
    curve_dir.mkdir(parents=True)
    uploaded = upload_dir / "managed.las"
    external = workspace / "external.las"
    uploaded.write_text("managed", encoding="utf-8")
    external.write_text("external", encoding="utf-8")

    managed = client.post(
        "/api/v1/domain/las-files",
        json={"well_id": well["id"], "filename": uploaded.name, "path": str(uploaded)},
    ).json()
    curve = curve_dir / f"{managed['id']}.json"
    curve.write_text("[]", encoding="utf-8")
    client.put(
        f"/api/v1/domain/las-files/{managed['id']}",
        json={
            "well_id": well["id"],
            "filename": uploaded.name,
            "path": str(uploaded),
            "curve_data_path": str(curve),
        },
    )
    external_record = client.post(
        "/api/v1/domain/las-files",
        json={"well_id": well["id"], "filename": external.name, "path": str(external)},
    ).json()

    assert client.delete(f"/api/v1/domain/las-files/{managed['id']}").status_code == 200
    assert not uploaded.exists()
    assert not curve.exists()
    assert client.delete(f"/api/v1/domain/las-files/{external_record['id']}").status_code == 200
    assert external.exists()


def test_store_reads_legacy_json_and_writes_versioned_backup(tmp_path):
    from app.domain.store import DomainStore, SCHEMA_VERSION

    path = tmp_path / "domain.json"
    path.write_text(json.dumps({"wells": [{"id": "legacy", "name": "Legacy"}]}), encoding="utf-8")
    store = DomainStore(path)

    assert store.get("wells", "legacy")["name"] == "Legacy"
    store.update("wells", "legacy", {"status": "drilling"})

    current = json.loads(path.read_text(encoding="utf-8"))
    backup = json.loads((tmp_path / "domain.json.bak").read_text(encoding="utf-8"))
    assert current["schema_version"] == SCHEMA_VERSION
    assert backup.get("schema_version") is None
    assert backup["wells"][0]["name"] == "Legacy"


def test_store_atomic_replace_failure_preserves_original(monkeypatch, tmp_path):
    import app.domain.store as store_module
    from app.domain.store import DomainStore

    path = tmp_path / "domain.json"
    store = DomainStore(path)
    store.create("wells", {"name": "Original"})
    original = path.read_text(encoding="utf-8")

    def fail_replace(source, target):
        assert str(source).endswith(".tmp")
        assert target == path
        raise OSError("replace failed")

    monkeypatch.setattr(store_module.os, "replace", fail_replace)
    with pytest.raises(OSError, match="replace failed"):
        store.create("wells", {"name": "Not committed"})

    assert path.read_text(encoding="utf-8") == original
    assert list(tmp_path.glob("*.tmp")) == []


def test_store_process_lock_prevents_lost_updates(tmp_path):
    from app.domain.store import DomainStore

    store = DomainStore(tmp_path / "domain.json")
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(lambda index: store.create("wells", {"name": f"W-{index}"}), range(40)))
    assert len(store.list("wells")) == 40
