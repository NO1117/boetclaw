"""Phase 9 tests: cron service CRUD/trigger + heartbeat, automation source."""

import pytest


def test_cron_add_list_remove(tmp_path):
    from app.services.cron_service import CronService

    svc = CronService(store_path=tmp_path / "cron.json")
    job = svc.add_job("daily", "0 8 * * *", "汇总日报", channel="feishu")
    assert job.id in {j.id for j in svc.list_jobs()}
    assert svc.get(job.id).cron == "0 8 * * *"
    # persisted to disk
    svc2 = CronService(store_path=tmp_path / "cron.json")
    assert job.id in {j.id for j in svc2.list_jobs()}
    assert svc.remove(job.id) is True
    assert svc.remove("nope") is False


@pytest.mark.asyncio
async def test_cron_run_job_uses_cron_source(tmp_path):
    from app.services.cron_service import CronService

    svc = CronService(store_path=tmp_path / "cron.json")
    captured = {}

    async def fake_runner(prompt, *, source, agent_id="default"):
        captured["prompt"] = prompt
        captured["source"] = source
        return {"response": "ok"}

    svc.runner = fake_runner
    job = svc.add_job("j", "*/1 * * * *", "ping")
    await svc._run_job(job.id)
    assert captured["source"] == "cron"
    assert captured["prompt"] == "ping"
    assert svc.get(job.id).last_run != ""
    assert svc.get(job.id).last_status == "success"
    assert len(svc.history(job.id)) == 1


@pytest.mark.asyncio
async def test_cron_run_job_missing_or_disabled(tmp_path):
    from app.services.cron_service import CronService

    svc = CronService(store_path=tmp_path / "cron.json")
    # missing id -> no error
    await svc._run_job("missing")
    job = svc.add_job("j", "*/1 * * * *", "ping", enabled=False)
    called = {"n": 0}

    async def fake_runner(prompt, *, source, agent_id="default"):
        called["n"] += 1
        return {"response": "ok"}

    svc.runner = fake_runner
    await svc._run_job(job.id)
    assert called["n"] == 0


@pytest.mark.asyncio
async def test_heartbeat_beat_uses_heartbeat_source():
    from app.services.heartbeat import HeartbeatService

    svc = HeartbeatService()
    captured = {}

    async def fake_runner(prompt, *, source):
        captured["source"] = source
        return {"response": "ok"}

    svc.runner = fake_runner
    await svc._beat()
    assert captured["source"] == "heartbeat"


def test_cron_source_not_persisted_memory():
    from app.memory.context_policy import should_persist_memory

    assert should_persist_memory("cron") is False
    assert should_persist_memory("heartbeat") is False


def test_invalid_crontab_raises(tmp_path):
    from app.services.cron_service import CronService

    svc = CronService(store_path=tmp_path / "cron.json")
    svc.start()  # needs a running scheduler to schedule + validate
    try:
        with pytest.raises(Exception):
            svc.add_job("bad", "not-a-cron", "x")
    finally:
        svc.shutdown()


@pytest.mark.asyncio
async def test_cron_update_enable_trigger_and_failure_history(tmp_path):
    from app.services.cron_service import CronService

    svc = CronService(store_path=tmp_path / "cron.json")
    job = svc.add_job("j", "*/1 * * * *", "ping", enabled=False)

    updated = svc.update_job(job.id, name="j2", prompt="pong", enabled=True)
    assert updated is not None
    assert updated.name == "j2"
    assert updated.prompt == "pong"
    assert updated.enabled is True

    async def failing_runner(prompt, *, source, agent_id="default"):
        raise RuntimeError("boom")

    svc.runner = failing_runner
    record = await svc.trigger(job.id)
    assert record is not None
    assert record.status == "failed"
    assert "boom" in record.error
    assert svc.get(job.id).last_status == "failed"
    assert svc.get(job.id).last_error == "boom"

    disabled = svc.set_enabled(job.id, False)
    assert disabled is not None and disabled.enabled is False
    assert await svc.trigger(job.id) is None
