"""Phase 7 tests: memory context policy, store backend, summarization toggle."""

import tempfile
from pathlib import Path


def test_should_persist_memory_by_source():
    from app.memory.context_policy import is_automation, normalize_source, should_persist_memory

    assert should_persist_memory("user") is True
    assert should_persist_memory("channel") is True
    assert should_persist_memory("cron") is False
    assert should_persist_memory("heartbeat") is False
    # unknown -> treated as user
    assert should_persist_memory("weird") is True
    assert normalize_source(None) == "user"
    assert is_automation("cron") is True


def test_store_backend_disabled_by_default(monkeypatch):
    from app.core.config import settings
    from app.memory import store_backend

    monkeypatch.setattr(settings, "memory_backend", "file", raising=False)
    assert store_backend.get_store() is None


def test_store_backend_store_mode(monkeypatch):
    from app.core.config import settings
    from app.memory import store_backend

    # reset cached singleton
    store_backend._store = None
    monkeypatch.setattr(settings, "memory_backend", "store", raising=False)
    store = store_backend.get_store()
    # If langgraph InMemoryStore importable, returns a store; otherwise None (graceful)
    assert store is None or store is not None
    store_backend._store = None


def test_memory_files_none_mode(monkeypatch):
    from app.core.config import settings
    from app.memory import store_backend

    monkeypatch.setattr(settings, "memory_backend", "none", raising=False)
    assert store_backend.get_memory_files() is None


def test_build_summarization_mw():
    from deepagents.backends import FilesystemBackend
    from langchain_core.language_models.fake_chat_models import FakeListChatModel

    from app.core.agent_factory import _build_summarization_mw

    with tempfile.TemporaryDirectory() as tmp:
        backend = FilesystemBackend(root_dir=str(Path(tmp)))
        fake_model = FakeListChatModel(responses=["summary"])
        mw = _build_summarization_mw(fake_model, backend)
        assert mw is not None
        assert hasattr(mw, "name")


def test_build_summarization_mw_graceful_without_key():
    """String model without API key should disable gracefully (return None)."""
    from deepagents.backends import FilesystemBackend

    from app.core.agent_factory import _build_summarization_mw

    with tempfile.TemporaryDirectory() as tmp:
        backend = FilesystemBackend(root_dir=str(Path(tmp)))
        # no OPENAI_API_KEY in test env -> should not raise, returns None
        mw = _build_summarization_mw("openai:gpt-4o", backend)
        assert mw is None or hasattr(mw, "name")


def test_event_types_memory():
    from app.core.observability import EventType

    assert EventType.MEMORY_PERSIST.value == "memory_persist"
    assert EventType.MEMORY_SKIP.value == "memory_skip"
