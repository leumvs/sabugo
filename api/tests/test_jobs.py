import asyncio
import multiprocessing
import os
import shutil
import tempfile
import time
from pathlib import Path

import pytest

from errors import ApiError
from services.jobs import Job, Jobs, UploadAllowance
from services.processing import run_analysis
from settings import Settings


def test_fifo_capacity_failure_recovery_and_two_subscribers(tmp_path):
    async def scenario():
        release = asyncio.Event()
        order = []
        active = 0
        async def runner(job, emit):
            nonlocal active
            active += 1
            assert active == 1
            order.append(job.filename)
            await release.wait()
            active -= 1
            if job.filename == "bad":
                raise ApiError("INVALID_IMAGE")
            emit("progress", {"stage": "load", "percent": 5})
            return {"results": []}, "csv"
        jobs = Jobs(runner, max_depth=2, ttl=0.02)
        def job(name):
            directory = Path(tempfile.mkdtemp(dir=tmp_path))
            return Job(directory / "input.png", name, 300, {}, [])
        first, bad, last = job("first"), job("bad"), job("last")
        a, b = jobs.subscribe(first), jobs.subscribe(first)
        assert jobs.enqueue(first) == 0
        await asyncio.sleep(0)
        assert jobs.enqueue(bad) == 1
        assert jobs.enqueue(last) == 2
        refused = job("refused")
        with pytest.raises(ApiError, match="SERVICE_AT_CAPACITY"):
            jobs.enqueue(refused)
        shutil.rmtree(refused.image_path.parent)
        release.set()
        await jobs.task
        assert order == ["first", "bad", "last"]
        assert first.status == last.status == "completed"
        assert bad.status == "failed"
        for listener in (a, b):
            events = [listener.get_nowait()[0] for _ in range(listener.qsize())]
            assert events == ["queued", "started", "progress", "completed"]
            jobs.unsubscribe(first.id, listener)
        assert not jobs.listeners
        assert not any(job.image_path.parent.exists() for job in (first, bad, last))
        await asyncio.sleep(0.03)
        assert not jobs.jobs
        await jobs.close()
    asyncio.run(scenario())


def _stall(connection, job, max_megapixels):
    time.sleep(30)


def test_timeout_and_cancellation_kill_children(job_factory, monkeypatch):
    import services.processing as processing
    monkeypatch.setattr(processing, "_process", _stall)
    before = {child.pid for child in multiprocessing.active_children()}
    async def scenario():
        with pytest.raises(ApiError, match="PROCESSING_TIMEOUT"):
            await run_analysis(job_factory(), lambda *args: None, Settings(JOB_TIMEOUT_SECONDS=0.05))
        assert {child.pid for child in multiprocessing.active_children()} == before
        task = asyncio.create_task(run_analysis(job_factory(), lambda *args: None, Settings()))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert {child.pid for child in multiprocessing.active_children()} == before
    asyncio.run(scenario())


def test_shutdown_cleans_active_and_waiting_uploads(tmp_path):
    async def scenario():
        async def runner(job, emit):
            await asyncio.sleep(30)
        jobs = Jobs(runner)
        pending = []
        for name in ("active", "waiting"):
            directory = Path(tempfile.mkdtemp(dir=tmp_path))
            job = Job(directory / "input.png", name, 300, {}, [])
            pending.append(job)
            jobs.enqueue(job)
        await asyncio.sleep(0)
        await jobs.close()
        assert not jobs.jobs and not jobs.waiting and not jobs.expiry
        assert all(not job.image_path.parent.exists() for job in pending)
    asyncio.run(scenario())


def test_upload_reservation_releases_on_error_and_can_commit(job_factory):
    async def scenario():
        async def runner(job, emit):
            return {"results": []}, ""
        jobs = Jobs(runner, max_depth=1)
        with pytest.raises(ValueError):
            with jobs.reserve_upload():
                with pytest.raises(ApiError, match="SERVICE_AT_CAPACITY"):
                    jobs.check_capacity()
                raise ValueError("invalid_upload")
        assert jobs.uploading == 0
        with jobs.reserve_upload():
            jobs.enqueue(job_factory(), reserved=True)
        assert jobs.uploading == 0
        await jobs.task
        await jobs.close()
        with pytest.raises(ApiError, match="SERVICE_AT_CAPACITY"):
            with jobs.reserve_upload():
                pass
    asyncio.run(scenario())


def test_late_subscribers_receive_current_state_and_last_progress(job_factory):
    async def scenario():
        release = asyncio.Event()
        async def runner(job, emit):
            emit("progress", {"stage": "segment", "percent": 20})
            await release.wait()
            return {"results": []}, "csv"
        jobs = Jobs(runner)
        first, waiting = job_factory(), job_factory()
        jobs.enqueue(first)
        await asyncio.sleep(0)
        jobs.enqueue(waiting)
        active = jobs.subscribe(first)
        queued = jobs.subscribe(waiting)
        assert active.get_nowait() == ("started", {})
        assert active.get_nowait() == ("progress", {"stage": "segment", "percent": 20})
        assert queued.get_nowait() == ("queued", {"queuePosition": 1})
        release.set()
        await jobs.task
        terminal = jobs.subscribe(first)
        assert terminal.qsize() == 1
        assert terminal.get_nowait() == ("completed", {"results": []})
        for job, listener in ((first, active), (waiting, queued), (first, terminal)):
            jobs.unsubscribe(job.id, listener)
        assert not jobs.listeners
        await jobs.close()
    asyncio.run(scenario())


def test_rate_limit_expires_active_and_idle_addresses(monkeypatch):
    import services.jobs as module
    now = 0
    monkeypatch.setattr(module.time, "monotonic", lambda: now)
    allowance = UploadAllowance(1)
    allowance.check("idle")
    allowance.check("active")
    now = 3599
    with pytest.raises(ApiError, match="RATE_LIMITED"):
        allowance.check("active")
    now = 3600
    allowance.check("active")
    now = 3660
    allowance.check("new")
    assert "idle" not in allowance.addresses
    assert set(allowance.addresses) == {"active", "new"}


def _exit_early(connection, job, max_megapixels):
    os._exit(9)


def test_child_crash_is_sanitized_and_next_child_can_run(job_factory, monkeypatch):
    import services.processing as processing
    original = processing._process
    before = {child.pid for child in multiprocessing.active_children()}
    async def scenario():
        monkeypatch.setattr(processing, "_process", _exit_early)
        with pytest.raises(ApiError, match="INTERNAL_ERROR"):
            await run_analysis(job_factory(), lambda *args: None, Settings())
        monkeypatch.setattr(processing, "_process", original)
        result, _ = await run_analysis(job_factory(), lambda *args: None, Settings())
        assert result["results"]
        assert {child.pid for child in multiprocessing.active_children()} == before
    asyncio.run(scenario())
