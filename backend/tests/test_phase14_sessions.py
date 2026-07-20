"""Phase 14.6 tests: chat session history store."""

from pathlib import Path


def test_session_store_records_lists_and_exports(tmp_path: Path):
    from app.memory.session_store import SessionStore

    store = SessionStore(tmp_path)
    store.record_turn(
        thread_id="thread-1",
        agent_id="default",
        user_message="查询 XX-1 井",
        assistant_message="已完成查询",
        trace_id="trace-1",
        run_id="run-1",
    )

    sessions = store.list_sessions("XX-1")
    assert len(sessions) == 1
    assert sessions[0]["thread_id"] == "thread-1"
    assert sessions[0]["message_count"] == 2
    assert sessions[0]["last_trace_id"] == "trace-1"

    detail = store.get_session("thread-1")
    assert detail is not None
    assert detail["messages"][0]["role"] == "user"

    exported = store.export_markdown("thread-1")
    assert exported is not None
    assert "# BoetClaw Session thread-1" in exported
    assert "已完成查询" in exported

    assert store.delete_session("thread-1") is True
    assert store.get_session("thread-1") is None
    assert store.delete_session("thread-1") is False


def test_session_store_archive_hides_from_default_list(tmp_path: Path):
    from app.memory.session_store import SessionStore

    store = SessionStore(tmp_path)
    store.record_turn(
        thread_id="thread-active",
        agent_id="default",
        user_message="活跃会话",
        assistant_message="ok",
    )
    store.record_turn(
        thread_id="thread-archive",
        agent_id="default",
        user_message="待归档",
        assistant_message="ok",
    )

    archived = store.archive_session("thread-archive")
    assert archived is not None
    assert archived["archived"] is True
    assert archived["archived_at"]

    active = store.list_sessions()
    assert [row["thread_id"] for row in active] == ["thread-active"]
    assert active[0]["archived"] is False

    all_rows = store.list_sessions(include_archived=True)
    assert {row["thread_id"] for row in all_rows} == {"thread-active", "thread-archive"}

    only_archived = store.list_sessions(archived_only=True)
    assert len(only_archived) == 1
    assert only_archived[0]["thread_id"] == "thread-archive"
    assert only_archived[0]["archived"] is True

    restored = store.unarchive_session("thread-archive")
    assert restored is not None
    assert restored["archived"] is False
    assert restored["archived_at"] == ""
    assert {row["thread_id"] for row in store.list_sessions()} == {"thread-active", "thread-archive"}


async def test_session_delete_api(tmp_path: Path, monkeypatch):
    from fastapi import HTTPException

    from app.api.routes import agent as agent_routes
    from app.memory.session_store import session_store

    monkeypatch.setattr(session_store, "root", tmp_path / "sessions", raising=False)
    session_store.record_turn(
        thread_id="thread-delete",
        agent_id="default",
        user_message="删除测试",
        assistant_message="准备删除",
    )

    assert await agent_routes.delete_session("thread-delete") == {"deleted": "thread-delete"}
    assert session_store.get_session("thread-delete") is None

    try:
        await agent_routes.delete_session("thread-delete")
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("expected HTTPException")


async def test_session_archive_api(tmp_path: Path, monkeypatch):
    from fastapi import HTTPException

    from app.api.routes import agent as agent_routes
    from app.memory.session_store import session_store

    monkeypatch.setattr(session_store, "root", tmp_path / "sessions", raising=False)
    session_store.record_turn(
        thread_id="thread-arch",
        agent_id="default",
        user_message="归档测试",
        assistant_message="准备归档",
    )

    archived = await agent_routes.archive_session("thread-arch")
    assert archived["thread_id"] == "thread-arch"
    assert archived["archived"] is True
    assert archived["archived_at"]

    listed = await agent_routes.list_sessions()
    assert listed["sessions"] == []

    listed_archived = await agent_routes.list_sessions(archived_only=True)
    assert len(listed_archived["sessions"]) == 1
    assert listed_archived["sessions"][0]["thread_id"] == "thread-arch"

    unarchived = await agent_routes.unarchive_session("thread-arch")
    assert unarchived == {"thread_id": "thread-arch", "archived": False, "archived_at": ""}
    listed_again = await agent_routes.list_sessions()
    assert listed_again["sessions"][0]["thread_id"] == "thread-arch"

    try:
        await agent_routes.archive_session("missing-thread")
    except HTTPException as exc:
        assert exc.status_code == 404
    else:
        raise AssertionError("expected HTTPException")
