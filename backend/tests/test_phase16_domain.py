"""Phase 16.1 tests: drilling domain models and JSON store."""


def test_domain_store_crud(tmp_path):
    from app.domain.store import DomainStore

    store = DomainStore(tmp_path / "domain.json")
    well = store.create("wells", {"name": "XX-1", "status": "drilling"})
    assert well["id"]
    assert store.get("wells", well["id"])["name"] == "XX-1"

    updated = store.update("wells", well["id"], {"status": "completed"})
    assert updated is not None
    assert updated["status"] == "completed"

    store2 = DomainStore(tmp_path / "domain.json")
    assert store2.get("wells", well["id"])["status"] == "completed"
    assert store2.delete("wells", well["id"]) is True


def test_domain_routes_create_related_objects(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.domain.store import domain_store
    from app.main import app

    monkeypatch.setattr(domain_store, "path", tmp_path / "domain.json", raising=False)
    client = TestClient(app)

    res = client.post("/api/v1/domain/wells", json={"name": "XX-1", "field": "Boet"})
    assert res.status_code == 200
    well_id = res.json()["id"]

    res = client.post(
        "/api/v1/domain/sections",
        json={"well_id": well_id, "name": "12-1/4", "top_depth": 0, "bottom_depth": 1200},
    )
    assert res.status_code == 200
    assert res.json()["well_id"] == well_id

    res = client.post(
        "/api/v1/domain/reports",
        json={"well_id": well_id, "report_date": "2026-07-14", "summary": "正常钻进"},
    )
    assert res.status_code == 200

    res = client.post("/api/v1/domain/params", json={"well_id": well_id, "measured_depth": 1000, "wob": 12})
    assert res.status_code == 200

    res = client.post(
        "/api/v1/domain/las-files",
        json={"well_id": well_id, "filename": "xx-1.las", "curves": ["GR", "RT"]},
    )
    assert res.status_code == 200

    assert len(client.get(f"/api/v1/domain/sections?well_id={well_id}").json()) == 1
    assert len(client.get(f"/api/v1/domain/reports?well_id={well_id}").json()) == 1
    assert len(client.get(f"/api/v1/domain/params?well_id={well_id}").json()) == 1
    assert len(client.get(f"/api/v1/domain/las-files?well_id={well_id}").json()) == 1


def test_domain_routes_reject_related_object_for_missing_well(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.domain.store import domain_store
    from app.main import app

    monkeypatch.setattr(domain_store, "path", tmp_path / "domain.json", raising=False)
    client = TestClient(app)

    res = client.post("/api/v1/domain/params", json={"well_id": "missing", "measured_depth": 100})
    assert res.status_code == 404
