"""Phase 16.3 tests: domain-backed drilling parameter tool."""

import json


def test_query_drilling_params_uses_domain_data(monkeypatch, tmp_path):
    from app.domain.store import domain_store
    from app.tools.builtin import query_drilling_params

    monkeypatch.setattr(domain_store, "path", tmp_path / "domain.json", raising=False)
    well = domain_store.create("wells", {"name": "XX-1"})
    domain_store.create(
        "params",
        {
            "well_id": well["id"],
            "measured_depth": 1200,
            "wob": 88,
            "rpm": 66,
            "rop": 9.5,
            "source": "manual",
        },
    )

    result = json.loads(query_drilling_params.invoke({"well_id": "XX-1", "depth_range": "1000-1300"}))
    assert result["source"] == "domain"
    assert result["records"][0]["well_id"] == "XX-1"
    assert result["records"][0]["depth"] == 1200
    assert result["records"][0]["wob"] == 88


def test_query_drilling_params_falls_back_to_mock(monkeypatch, tmp_path):
    from app.domain.store import domain_store
    from app.tools.builtin import query_drilling_params

    monkeypatch.setattr(domain_store, "path", tmp_path / "domain.json", raising=False)
    result = json.loads(query_drilling_params.invoke({"well_id": "missing", "depth_range": "0-100"}))

    assert result["source"] == "mock"
    assert len(result["records"]) > 0
    assert result["records"][0]["source"] == "mock"
