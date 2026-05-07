"""Tests fuer services.brain_v3.background_queue.

Plan-Doc 06 Phase 2 DoD: Background-Queue + Progress.
Pure asyncio + threading, kein GPU/Modell noetig.

Vermeidet pytest-asyncio Dependency: nutzt asyncio.run() pro Test.
"""
from __future__ import annotations

import asyncio

from services.brain_v3.background_queue import (
    EmbeddingJob, EmbeddingJobQueue, JobProgress, JobStatus,
)


def test_submit_and_run_simple_job():
    async def scenario():
        q = EmbeddingJobQueue(n_workers=1)
        q.start()
        try:
            async def work(progress_cb):
                progress_cb(0.5, "halfway")
                return 42
            job_id = await q.submit(EmbeddingJob(label="test", run=work))
            await q._queue.join()
            return q.get_progress(job_id)
        finally:
            await q.stop(drain=False)
    prog = asyncio.run(scenario())
    assert prog is not None
    assert prog.status == JobStatus.DONE
    assert prog.progress == 1.0
    assert prog.result == 42


def test_progress_subscriber_receives_updates():
    received: list[JobProgress] = []

    async def scenario():
        q = EmbeddingJobQueue(n_workers=1)
        q.start()
        q.subscribe(lambda p: received.append(p))
        try:
            async def work(progress_cb):
                progress_cb(0.25, "a")
                progress_cb(0.5, "b")
                progress_cb(0.75, "c")
                return None
            await q.submit(EmbeddingJob(label="t", run=work))
            await q._queue.join()
        finally:
            await q.stop(drain=False)

    asyncio.run(scenario())
    statuses = [p.status for p in received]
    assert JobStatus.PENDING in statuses
    assert JobStatus.RUNNING in statuses
    assert JobStatus.DONE in statuses
    progress_vals = [p.progress for p in received]
    assert any(p >= 0.5 for p in progress_vals)


def test_failed_job_marked_failed():
    async def scenario():
        q = EmbeddingJobQueue(n_workers=1)
        q.start()
        try:
            async def boom(_progress_cb):
                raise RuntimeError("intentional")
            job_id = await q.submit(EmbeddingJob(label="boom", run=boom))
            await q._queue.join()
            return q.get_progress(job_id)
        finally:
            await q.stop(drain=False)
    prog = asyncio.run(scenario())
    assert prog.status == JobStatus.FAILED
    assert "intentional" in prog.error


def test_jobs_serialize_with_one_worker():
    """Mit n_workers=1: zwei Jobs koennen sich nicht ueberlappen."""
    events: list[tuple[str, str]] = []

    async def scenario():
        q = EmbeddingJobQueue(n_workers=1)
        q.start()
        try:
            def make_job(name: str) -> EmbeddingJob:
                async def work(_pc):
                    events.append((name, "enter"))
                    await asyncio.sleep(0.05)
                    events.append((name, "exit"))
                return EmbeddingJob(label=name, run=work)

            await q.submit(make_job("A"))
            await q.submit(make_job("B"))
            await q._queue.join()
        finally:
            await q.stop(drain=False)

    asyncio.run(scenario())
    seq = [e for _n, e in events]
    assert seq == ["enter", "exit", "enter", "exit"]


def test_jobs_can_run_in_parallel_with_two_workers():
    enter_count = {"v": 0}
    max_concurrent = {"v": 0}

    async def scenario():
        q = EmbeddingJobQueue(n_workers=2)
        q.start()
        try:
            def make_job() -> EmbeddingJob:
                async def work(_pc):
                    enter_count["v"] += 1
                    max_concurrent["v"] = max(max_concurrent["v"], enter_count["v"])
                    await asyncio.sleep(0.05)
                    enter_count["v"] -= 1
                return EmbeddingJob(label="x", run=work)

            for _ in range(4):
                await q.submit(make_job())
            await q._queue.join()
        finally:
            await q.stop(drain=False)

    asyncio.run(scenario())
    assert max_concurrent["v"] >= 2


def test_pending_count_reflects_queue_size():
    async def scenario():
        q = EmbeddingJobQueue(n_workers=1)
        async def work(_pc):
            await asyncio.sleep(0.01)
        await q.submit(EmbeddingJob(label="a", run=work))
        await q.submit(EmbeddingJob(label="b", run=work))
        size_before_start = q.pending_count
        q.start()
        await q._queue.join()
        size_after_drain = q.pending_count
        await q.stop(drain=False)
        return size_before_start, size_after_drain

    before, after = asyncio.run(scenario())
    assert before == 2
    assert after == 0


def test_subscriber_exception_does_not_kill_queue():
    async def scenario():
        q = EmbeddingJobQueue(n_workers=1)
        q.start()
        def bad_sub(_p):
            raise RuntimeError("ignored")
        q.subscribe(bad_sub)
        try:
            async def work(_pc):
                return "ok"
            job_id = await q.submit(EmbeddingJob(label="t", run=work))
            await q._queue.join()
            return q.get_progress(job_id)
        finally:
            await q.stop(drain=False)

    prog = asyncio.run(scenario())
    assert prog.status == JobStatus.DONE
    assert prog.result == "ok"
