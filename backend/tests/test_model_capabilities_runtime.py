"""Tests for model capabilities, compatibility, graph cache and run metrics."""

from __future__ import annotations

import asyncio

import pytest


def test_tri_state_unknown_not_false():
    from app.providers.capabilities import ModelCapabilities, enrich_model

    info = enrich_model(name="unknown-model", provider="ollama")
    assert info.capabilities.vision is None
    assert info.to_dict()["capabilities"]["vision"] == "unknown"
    assert info.to_dict()["supports_vision"] is None


def test_static_metadata_merges_openai():
    from app.providers.capabilities import enrich_model

    info = enrich_model(name="gpt-4o", provider="openai")
    assert info.capabilities.vision is True
    assert info.context_window == 128_000
    assert info.pricing.get("input_per_million") == 2.50


def test_dynamic_overrides_static(monkeypatch, tmp_path):
    from app.providers.capability_cache import CapabilityCache
    from app.providers.capabilities import enrich_model, learn_capabilities, ModelCapabilities

    cache = CapabilityCache(path=tmp_path / "caps.json")
    monkeypatch.setattr("app.providers.capabilities.get_capability_cache", lambda: cache)
    learn_capabilities("ollama:llama", ModelCapabilities(vision=True))
    info = enrich_model(name="llama", provider="ollama")
    assert info.capabilities.vision is True
    assert info.capability_sources.get("vision") == "dynamic"


def test_compatibility_rejects_non_vision():
    from app.providers.compatibility import (
        check_model_compatibility,
        derive_input_requirements,
        ModelCompatibilityError,
    )

    req = derive_input_requirements(has_images=True, image_count=1)
    result = check_model_compatibility("openai", "o1", req)
    assert result.status == "incompatible"
    assert "vision" in result.missing_capabilities

    err = ModelCompatibilityError("bad", missing_capabilities=["vision"], provider="openai", model="o1")
    assert err.to_detail()["error_code"] == "MODEL_INCOMPATIBLE"


def test_compatibility_unknown_allows_with_warning():
    from app.providers.compatibility import check_model_compatibility, derive_input_requirements

    req = derive_input_requirements(has_images=True, image_count=1)
    result = check_model_compatibility("ollama", "qwen2.5", req)
    assert result.status == "unknown_risk"
    assert result.warnings


@pytest.mark.asyncio
async def test_graph_cache_hit_and_lru():
    from app.agents.graph_cache import AgentGraphCache

    cache = AgentGraphCache(max_size=2, ttl_seconds=60)
    builds = 0

    async def builder():
        nonlocal builds
        builds += 1
        return f"agent-{builds}"

    a1, hit1, _ = await cache.get_or_build("k1", builder)
    a2, hit2, _ = await cache.get_or_build("k1", builder)
    assert hit1 is False
    assert hit2 is True
    assert a1 == a2
    assert builds == 1

    await cache.get_or_build("k2", builder)
    await cache.get_or_build("k3", builder)
    assert cache.stats.evictions >= 1


@pytest.mark.asyncio
async def test_graph_cache_single_flight():
    from app.agents.graph_cache import AgentGraphCache

    cache = AgentGraphCache(max_size=8, ttl_seconds=60)
    builds = 0
    gate = asyncio.Event()

    async def builder():
        nonlocal builds
        builds += 1
        await gate.wait()
        return "shared"

    tasks = [asyncio.create_task(cache.get_or_build("same", builder)) for _ in range(3)]
    await asyncio.sleep(0.05)
    assert builds == 1
    gate.set()
    results = await asyncio.gather(*tasks)
    assert all(r[0] == "shared" for r in results)


def test_run_metrics_null_tokens_and_cost():
    from app.services.run_metrics import RunMetricsTracker

    tracker = RunMetricsTracker()
    tracker.start(trace_id="t1", run_id="r1", agent_id="default", provider="openai", model="gpt-4o")
    summary = tracker.complete("t1", usage={"input_tokens": None, "output_tokens": None})
    assert summary is not None
    assert summary.input_tokens is None
    assert summary.output_tokens is None
    assert summary.estimated_cost is None


def test_run_metrics_cost_estimate_when_priced():
    from app.services.run_metrics import RunMetricsTracker

    tracker = RunMetricsTracker()
    tracker.start(trace_id="t2", run_id="r2", agent_id="default", provider="openai", model="gpt-4o")
    summary = tracker.complete("t2", usage={"input_tokens": 1_000_000, "output_tokens": 0})
    assert summary is not None
    assert summary.estimated_cost is not None
    assert summary.cost_is_estimate is True
