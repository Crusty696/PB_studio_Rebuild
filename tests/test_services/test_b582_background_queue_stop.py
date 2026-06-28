"""B-582 — Shutdown-Hang in EmbeddingJobQueue.stop(drain=True).

Bug: stop(drain=True) ruft `await self._queue.join()` VOR worker cancel.
Bei einem haengenden Job (Job ruft nie task_done weil er ewig laeuft)
blockiert join() unbegrenzt -> request_stop(timeout_ms=5000) laeuft in
Timeout -> App-Shutdown haengt.

Diese Tests beweisen:
1. stop(drain=True) kehrt auch bei einem haengenden Job schnell zurueck
   (statt unbegrenzt zu blockieren) und der haengende Job wird gecancelt.
2. Gegenprobe: bei einem schnell-fertigen Job bringt stop(drain=True) den
   Job weiter regulaer zu Ende (DONE, kein Cancel-Regress).

Pure asyncio, kein pytest-asyncio (Projekt-Konvention: asyncio.run pro Test).
"""
from __future__ import annotations

import asyncio

from services.brain.background_queue import (
    EmbeddingJob, EmbeddingJobQueue, JobStatus,
)


def test_stop_drain_does_not_hang_on_stuck_job():
    """Haengender Job -> stop(drain=True) blockiert NICHT unbegrenzt."""
    started = asyncio.Event()

    async def scenario():
        q = EmbeddingJobQueue(n_workers=1)
        q.start()
        try:
            async def stuck(_progress_cb):
                started.set()
                await asyncio.sleep(60)  # haengt absichtlich

            job_id = await q.submit(EmbeddingJob(label="stuck", run=stuck))
            # Warten bis Worker den Job wirklich begonnen hat.
            await asyncio.wait_for(started.wait(), timeout=2)
            # Vor Fix: dieser wait_for laeuft in TimeoutError, weil stop()
            # auf dem unbegrenzten queue.join() haengt. Nach Fix kehrt stop
            # innerhalb von DRAIN_TIMEOUT_S (3s) + Cancel-Aufraeumung zurueck;
            # 8s Puffer beweist begrenzte (nicht-unbegrenzte) Rueckkehr.
            await asyncio.wait_for(q.stop(drain=True), timeout=8)
            return q.get_progress(job_id)
        finally:
            # Falls stop nicht sauber durchlief: hart aufraeumen.
            await q.stop(drain=False)

    prog = asyncio.run(scenario())
    # Haengender Job muss als gecancelt markiert sein.
    assert prog is not None
    assert prog.status == JobStatus.CANCELLED, prog.status


def test_stop_drain_finishes_quick_job():
    """Gegenprobe: schnell-fertiger Job wird bei drain=True zu Ende gebracht."""
    async def scenario():
        q = EmbeddingJobQueue(n_workers=1)
        q.start()
        try:
            async def quick(progress_cb):
                progress_cb(0.5, "halfway")
                await asyncio.sleep(0.02)
                return 99

            job_id = await q.submit(EmbeddingJob(label="quick", run=quick))
            await asyncio.wait_for(q.stop(drain=True), timeout=3)
            return q.get_progress(job_id)
        finally:
            await q.stop(drain=False)

    prog = asyncio.run(scenario())
    assert prog is not None
    assert prog.status == JobStatus.DONE, prog.status
    assert prog.result == 99
