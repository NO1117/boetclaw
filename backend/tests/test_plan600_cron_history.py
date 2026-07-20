"""PLAN-600: Cron run history persistence across service rebuild."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_cron_history_persists_across_service_rebuild(tmp_path):
    from app.services.cron_service import CronService

    jobs_path = tmp_path / "cron_jobs.json"
    history_path = tmp_path / "cron_history.json"
    first = CronService(store_path=jobs_path, history_path=history_path)

    async def fake_runner(prompt, *, source, agent_id="default"):
        return {"response": "ok", "trace_id": "t1", "run_id": "r1"}

    first.runner = fake_runner
    job = first.add_job("daily", "0 8 * * *", "汇总日报")
    await first._run_job(job.id)
    assert len(first.history(job.id)) == 1
    assert history_path.exists()

    second = CronService(store_path=jobs_path, history_path=history_path)
    rows = second.history(job.id)
    assert len(rows) == 1
    assert rows[0].status == "success"
    assert rows[0].trace_id == "t1"
    assert rows[0].run_id == "r1"
    assert rows[0].job_name == "daily"


@pytest.mark.asyncio
async def test_cron_history_truncates_to_limit(tmp_path, monkeypatch):
    from app.services.cron_service import CronService

    monkeypatch.setattr(CronService, "HISTORY_LIMIT", 3)
    svc = CronService(
        store_path=tmp_path / "jobs.json",
        history_path=tmp_path / "history.json",
    )

    async def fake_runner(prompt, *, source, agent_id="default"):
        return {"response": "ok"}

    svc.runner = fake_runner
    job = svc.add_job("burst", "*/1 * * * *", "ping")
    for _ in range(5):
        await svc._run_job(job.id)

    assert len(svc.history()) == 3
    restored = CronService(
        store_path=tmp_path / "jobs.json",
        history_path=tmp_path / "history.json",
    )
    assert len(restored.history()) == 3


def test_cron_history_tolerates_corrupt_file(tmp_path):
    from app.services.cron_service import CronService

    history_path = tmp_path / "history.json"
    history_path.write_text("{not-json", encoding="utf-8")
    svc = CronService(store_path=tmp_path / "jobs.json", history_path=history_path)
    assert svc.history() == []
