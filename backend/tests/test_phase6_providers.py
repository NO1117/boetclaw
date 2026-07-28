"""Phase 6 tests: provider abstraction, manager, capability cache."""

import tempfile
from pathlib import Path

import pytest


def test_manager_lists_three_providers():
    from app.providers.manager import provider_manager

    names = {p.name for p in provider_manager.list_providers()}
    assert {"openai", "anthropic", "ollama"} <= names


def test_parse_model_string():
    from app.providers.manager import provider_manager

    assert provider_manager.parse_model_string("openai:gpt-4o") == ("openai", "gpt-4o")
    assert provider_manager.parse_model_string("ollama:qwen2.5") == ("ollama", "qwen2.5")
    # no colon -> falls back to configured provider
    prov, model = provider_manager.parse_model_string("gpt-4o")
    assert model == "gpt-4o"


def test_provider_info_and_models():
    from app.providers.manager import provider_manager

    openai = provider_manager.get("openai")
    assert openai.default_model == "gpt-4o"
    models = provider_manager.list_models("openai")
    assert any(m.name == "gpt-4o" for m in models)

    ollama = provider_manager.get("ollama")
    assert ollama.requires_api_key is False


def test_unknown_provider_raises():
    from app.providers.manager import provider_manager

    with pytest.raises(ValueError):
        provider_manager.get("nope")


def test_capability_cache_roundtrip():
    from app.providers.capability_cache import CapabilityCache

    with tempfile.TemporaryDirectory() as tmp:
        cache = CapabilityCache(path=Path(tmp) / "cap.json")
        assert cache.get("openai:gpt-4o", "vision") is None
        cache.learn("openai:gpt-4o", "vision", True)
        assert cache.get("openai:gpt-4o", "vision") is True
        # reload from disk
        cache2 = CapabilityCache(path=Path(tmp) / "cap.json")
        assert cache2.get("openai:gpt-4o", "vision") is True


def test_ollama_check_returns_shape():
    from app.providers.manager import provider_manager

    result = provider_manager.check_connection("ollama")
    assert "connected" in result and "provider" in result
    assert result["provider"] == "ollama"


def test_openai_base_url_configures_local_compatible_model(monkeypatch):
    import langchain_openai

    from app.core.config import settings
    from app.providers.openai_provider import OpenAIProvider

    captured = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(settings, "openai_api_key", "", raising=False)
    monkeypatch.setattr(settings, "openai_base_url", "http://localhost:8001/v1", raising=False)
    monkeypatch.setattr(langchain_openai, "ChatOpenAI", FakeChatOpenAI)

    provider = OpenAIProvider()
    assert provider.is_configured() is True
    provider.get_chat_model("qwen2.5")

    assert captured["model"] == "qwen2.5"
    assert captured["base_url"] == "http://localhost:8001/v1"
    assert captured["api_key"] == "not-needed"


def test_anthropic_base_url_configures_proxy(monkeypatch):
    import langchain_anthropic

    from app.core.config import settings
    from app.providers.anthropic_provider import AnthropicProvider

    captured = {}

    class FakeChatAnthropic:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr(settings, "anthropic_api_key", "", raising=False)
    monkeypatch.setattr(settings, "anthropic_base_url", "http://localhost:8002", raising=False)
    monkeypatch.setattr(langchain_anthropic, "ChatAnthropic", FakeChatAnthropic)

    provider = AnthropicProvider()
    assert provider.is_configured() is True
    provider.get_chat_model("claude-local")

    assert captured["model"] == "claude-local"
    assert captured["base_url"] == "http://localhost:8002"
    assert captured["api_key"] == "not-needed"


def test_provider_config_routes_update_runtime_settings(monkeypatch, isolated_paths, master_key):
    from fastapi.testclient import TestClient

    from app.core.config import settings
    from app.main import app

    monkeypatch.setattr(settings, "openai_api_key", "", raising=False)
    monkeypatch.setattr(settings, "openai_base_url", "", raising=False)
    monkeypatch.setattr(settings, "llm_provider", "openai", raising=False)
    monkeypatch.setattr(settings, "llm_model", "gpt-4o", raising=False)

    client = TestClient(app)

    res = client.put(
        "/api/v1/providers/openai/config",
        json={"api_key": "sk-test", "base_url": "http://localhost:8001/v1"},
    )
    assert res.status_code == 200
    assert res.json()["api_key_configured"] is True
    assert res.json()["base_url"] == "http://localhost:8001/v1"
    assert "sk-test" not in res.text

    res = client.put("/api/v1/providers/default", json={"provider": "ollama", "model": "qwen2.5"})
    assert res.status_code == 200
    assert res.json()["model"] == "qwen2.5"


def test_provider_config_routes_do_not_persist_api_key_to_env(monkeypatch, tmp_path, master_key):
    from fastapi.testclient import TestClient

    from app.api.routes import providers as provider_routes
    from app.core.config import settings
    from app.credentials.vault import credential_vault
    from app.main import app
    from app.providers.connections.store import connection_store

    vault_path = tmp_path / "credentials" / "vault.json"
    conn_path = tmp_path / "provider_connections.json"
    monkeypatch.setattr(credential_vault, "_path", vault_path)
    monkeypatch.setattr(credential_vault, "_loaded", False)
    monkeypatch.setattr(credential_vault, "_records", {})
    monkeypatch.setattr(connection_store, "_path", conn_path)
    monkeypatch.setattr(connection_store, "_loaded", False)
    monkeypatch.setattr(connection_store, "_connections", {})
    monkeypatch.setattr(connection_store, "_default_connection_id", None)

    env_path = tmp_path / ".env"
    env_path.write_text(
        "LLM_PROVIDER=openai\n"
        "LLM_MODEL=gpt-4o\n"
        "# OPENAI_API_KEY=\n"
        "OPENAI_BASE_URL=\n"
        "OLLAMA_BASE_URL=http://localhost:11434\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(provider_routes, "PROVIDER_ENV_PATH", env_path, raising=False)
    monkeypatch.setattr(settings, "openai_api_key", "", raising=False)
    monkeypatch.setattr(settings, "openai_base_url", "", raising=False)

    client = TestClient(app)
    res = client.put(
        "/api/v1/providers/openai/config",
        json={"api_key": "sk-persist", "base_url": "http://localhost:8001/v1"},
    )
    assert res.status_code == 200

    content = env_path.read_text(encoding="utf-8")
    assert "OPENAI_API_KEY=sk-persist" not in content
    assert "sk-persist" not in content


def test_provider_rate_limiter_buckets_by_provider_model(monkeypatch):
    from app.core.config import settings
    from app.providers.rate_limiter import ProviderRateLimitError, ProviderRateLimiter

    limiter = ProviderRateLimiter()
    monkeypatch.setattr(settings, "provider_rate_limit_per_minute", 1, raising=False)

    limiter.check("openai", "gpt-4o")
    with pytest.raises(ProviderRateLimitError):
        limiter.check("openai", "gpt-4o")

    limiter.check("openai", "gpt-4o-mini")
    limiter.check("anthropic", "gpt-4o")


def test_provider_rate_limiter_disabled(monkeypatch):
    from app.core.config import settings
    from app.providers.rate_limiter import ProviderRateLimiter

    limiter = ProviderRateLimiter()
    monkeypatch.setattr(settings, "provider_rate_limit_per_minute", 0, raising=False)

    limiter.check("openai", "gpt-4o")
    limiter.check("openai", "gpt-4o")
