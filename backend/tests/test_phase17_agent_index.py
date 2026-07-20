"""Agent workspace file index and run history tests."""


def test_agent_files_and_history(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.agents.multi_agent_manager import multi_agent_manager
    from app.main import app
    from app.memory.session_store import session_store
    from app.services.task_scheduler import task_scheduler

    monkeypatch.setattr(multi_agent_manager, "_root", tmp_path / "agents", raising=False)
    monkeypatch.setattr(multi_agent_manager, "_ws", {}, raising=False)
    monkeypatch.setattr(task_scheduler, "_tasks", {}, raising=False)
    monkeypatch.setattr(session_store, "root", tmp_path / "sessions", raising=False)

    ws = multi_agent_manager.create("a1")
    ws.files_dir().mkdir(parents=True, exist_ok=True)
    (ws.files_dir() / "report.md").write_text("hello", encoding="utf-8")

    task = task_scheduler.create("Agent task", "do it", metadata={"agent_id": "a1"})
    session_store.record_turn(
        thread_id="thread-a1",
        agent_id="a1",
        user_message="hi",
        assistant_message="ok",
        trace_id="trace-a1",
        run_id="run-a1",
    )

    client = TestClient(app)
    res = client.get("/api/v1/agents/a1/files")
    assert res.status_code == 200
    assert res.json()["files"][0]["path"] == "report.md"

    res = client.get("/api/v1/agents/a1/history")
    assert res.status_code == 200
    history = res.json()["history"]
    assert {item["type"] for item in history} == {"task", "session"}
    assert any(item["id"] == task.id and item["match_source"] == "task.metadata.agent_id" for item in history)
    assert any(item["id"] == "thread-a1" and item["trace_id"] == "trace-a1" for item in history)
