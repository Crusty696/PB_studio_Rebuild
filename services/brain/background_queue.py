"""Brain V3 — Asynchrone Background-Queue fuer Embedding-Jobs.

Plan-Doc 06 Phase 2 explizit: "Background-Queue fuer asynchrone Berechnung
— asyncio.Queue + Worker-Task. Progress via SSE im events_router."

Design:
- `EmbeddingJob` ist eine generische Job-Beschreibung (audio_path / video_path
  + Callable die das Embedding produziert + Callable die persistiert).
- `EmbeddingJobQueue` ist ein asyncio.Queue mit konfigurierbarer Worker-Anzahl.
  Default 1 Worker (sequenziell), passend zu GpuSerializer-Realitaet.
- Progress wird via Subscriber-Callback gepusht (Plan: SSE-Bridge in
  events_router; hier nur das Async-API, keine HTTP-Bindung).

API ist V3-isoliert: greift nicht in bestehende `events_router` ein, das
ist Aufgabe der Phase-4-Pacing-Integration.
"""
from __future__ import annotations

import asyncio
import dataclasses
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger(__name__)


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class JobProgress:
    job_id: str
    status: JobStatus
    label: str
    progress: float = 0.0   # 0..1
    message: str = ""
    error: str = ""
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    result: Any = None


@dataclass
class EmbeddingJob:
    """Generischer Job — die eigentliche Arbeit ist eine async-Callable.

    Args:
        label: User-sichtbarer Name (z.B. "CLAP: my_mix.mp3")
        run: async function(progress_cb) -> result.
             progress_cb(progress: float, message: str) ist optional ufzurufen.
    """
    label: str
    run: Callable[[Callable[[float, str], None]], Awaitable[Any]]
    job_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])


# Subscriber-Signatur: synchron, soll schnell zurueckkehren (UI-Bridge).
ProgressSubscriber = Callable[[JobProgress], None]


class EmbeddingJobQueue:
    """asyncio.Queue + N Worker-Tasks. Default 1 (sequenziell)."""

    def __init__(self, n_workers: int = 1) -> None:
        if n_workers < 1:
            raise ValueError("n_workers muss >=1 sein")
        self.n_workers = n_workers
        self._queue: asyncio.Queue[EmbeddingJob] = asyncio.Queue()
        self._workers: list[asyncio.Task] = []
        self._progress: dict[str, JobProgress] = {}
        self._subscribers: list[ProgressSubscriber] = []
        self._stopped = False
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._workers:
            return
        for i in range(self.n_workers):
            t = asyncio.create_task(self._worker_loop(i), name=f"brain_v3_worker_{i}")
            self._workers.append(t)
        logger.info("EmbeddingJobQueue: %d worker(s) started", self.n_workers)

    # Timeout (Sekunden), wie lange stop(drain=True) auf pending Jobs wartet,
    # bevor haengende Worker hart gecancelt werden. Muss kleiner sein als der
    # App-Shutdown-Timeout (main.py: request_stop timeout_ms=5000), damit der
    # Shutdown nie am unbegrenzten queue.join() haengt (B-582).
    DRAIN_TIMEOUT_S = 3.0

    async def stop(self, drain: bool = True) -> None:
        """Stoppt Worker. drain=True wartet auf alle pending Jobs.

        B-582: drain wartet nur mit Timeout (DRAIN_TIMEOUT_S). Laeuft ein Job
        laenger (haengt), werden die Worker hart gecancelt statt unbegrenzt am
        queue.join() zu blockieren — sonst haengt der App-Shutdown.
        """
        if not self._workers:
            return
        self._stopped = True
        if drain:
            try:
                await asyncio.wait_for(self._queue.join(),
                                       timeout=self.DRAIN_TIMEOUT_S)
            except asyncio.TimeoutError:
                logger.warning(
                    "EmbeddingJobQueue: drain timeout nach %.1fs — haengende "
                    "Worker werden hart gecancelt", self.DRAIN_TIMEOUT_S)
        for w in self._workers:
            w.cancel()
        for w in self._workers:
            try:
                await w
            except (asyncio.CancelledError, Exception):
                pass
        self._workers.clear()
        logger.info("EmbeddingJobQueue: stopped")

    # ------------------------------------------------------------------
    # Submit + Subscribe
    # ------------------------------------------------------------------
    async def submit(self, job: EmbeddingJob) -> str:
        if self._stopped:
            raise RuntimeError("Queue ist gestoppt — keine neuen Jobs annehmen")
        progress = JobProgress(job_id=job.job_id, status=JobStatus.PENDING, label=job.label)
        async with self._lock:
            self._progress[job.job_id] = progress
        self._notify(progress)
        await self._queue.put(job)
        return job.job_id

    def subscribe(self, callback: ProgressSubscriber) -> None:
        self._subscribers.append(callback)

    def unsubscribe(self, callback: ProgressSubscriber) -> None:
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def get_progress(self, job_id: str) -> Optional[JobProgress]:
        return self._progress.get(job_id)

    def all_progress(self) -> dict[str, JobProgress]:
        return dict(self._progress)

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()

    # ------------------------------------------------------------------
    # Worker-Loop
    # ------------------------------------------------------------------
    async def _worker_loop(self, idx: int) -> None:
        logger.info("worker[%d] started", idx)
        while not self._stopped:
            try:
                job = await self._queue.get()
            except asyncio.CancelledError:
                break
            try:
                await self._run_job(job, worker_idx=idx)
            except Exception as exc:
                logger.exception("worker[%d] crashed on job %s: %s",
                                 idx, job.job_id, exc)
            finally:
                self._queue.task_done()
        logger.info("worker[%d] stopped", idx)

    async def _run_job(self, job: EmbeddingJob, *, worker_idx: int) -> None:
        progress = self._progress.get(job.job_id)
        if progress is None:
            progress = JobProgress(job_id=job.job_id, status=JobStatus.RUNNING,
                                   label=job.label)
            self._progress[job.job_id] = progress

        progress.status = JobStatus.RUNNING
        progress.started_at = time.time()
        progress.message = f"running on worker {worker_idx}"
        self._notify(progress)

        def progress_cb(value: float, message: str = "") -> None:
            progress.progress = max(0.0, min(1.0, float(value)))
            if message:
                progress.message = message
            self._notify(progress)

        try:
            result = await job.run(progress_cb)
            progress.status = JobStatus.DONE
            progress.progress = 1.0
            progress.result = result
            progress.message = "done"
        except asyncio.CancelledError:
            progress.status = JobStatus.CANCELLED
            progress.message = "cancelled"
            raise
        except Exception as exc:
            progress.status = JobStatus.FAILED
            progress.error = f"{type(exc).__name__}: {exc}"
            progress.message = "failed"
            logger.exception("Job %s failed: %s", job.job_id, exc)
        finally:
            progress.finished_at = time.time()
            self._notify(progress)

    def _notify(self, progress: JobProgress) -> None:
        # WICHTIG: Snapshot-Kopie, sonst sehen Subscriber alle den FINALEN
        # Status (gleiche Object-Referenz). Bug gefangen in pytest 2026-05-03.
        snapshot = dataclasses.replace(progress)
        for cb in list(self._subscribers):
            try:
                cb(snapshot)
            except Exception as exc:
                logger.warning("subscriber raised, continuing: %s", exc)
