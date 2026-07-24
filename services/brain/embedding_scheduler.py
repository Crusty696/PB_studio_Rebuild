"""Brain V3 — Embedding-Scheduler (Phase 2 App-Sync).

Brueckt asyncio-basierte EmbeddingJobQueue in den synchronen Qt-Welt:
- Eigener QThread hostet asyncio-Loop + EmbeddingJobQueue
- `submit_path()` ist thread-safe + nicht-blockierend fuer den UI-Thread
- Cache-Check vor Embedding (EmbeddingCache.lookup) → Cache-Hit-Skip
- Qt-Signal `job_progress` fuer Status-Updates an UI

Lifecycle:
- `start()` beim App-Boot (PBWindow.__init__ via QTimer.singleShot)
- `request_stop()` beim App-Shutdown (PBWindow.closeEvent)

Embedder werden lazy importiert — Tests koennen `embedder_factory` mocken.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, QThread, Signal

from services.brain.background_queue import (
    EmbeddingJob,
    EmbeddingJobQueue,
    JobProgress,
)
from services.brain.gpu_serializer import GpuSerializer, get_default_serializer
from services.brain.storage.embedding_cache import EmbeddingCache

logger = logging.getLogger(__name__)


@dataclass
class EmbeddingTask:
    media_hash: str
    media_type: str  # 'audio' | 'video'
    source_path: Path


class SkipEmbeddingError(Exception):
    """Signalisiert, dass ein Video/Audio-Medium unlesbar ist und uebersprungen werden soll."""
    pass


# Embedder-Fabrik: liefert Callable[[EmbeddingTask, ProgressCb], np.ndarray].
# Default = lazy import von ClapAudioEmbedder / Siglip2VideoEmbedder.
EmbedderFactory = Callable[[EmbeddingTask, Callable[[float, str], None], GpuSerializer], "object"]


# B-554: Persistente Embedder-Instanzen. Der Embedder cacht das Modell intern
# (``_vision`` / CLAP-Modell). Frueher erzeugte ``_default_embedder_factory`` pro
# Clip eine FRISCHE Instanz -> das Modell wurde fuer JEDEN Clip neu geladen
# (``from_pretrained`` + ``.to(cuda)``, je ~2 s, Stack-belegt in freeze_stacks).
# Eine wiederverwendete Instanz laedt das Modell EINMAL. Der Lock schuetzt den
# Lazy-Init, falls die Factory aus mehreren Worker-Threads aufgerufen wird.
_EMBEDDER_CACHE_LOCK = threading.Lock()
_VIDEO_EMBEDDER = None  # type: ignore[var-annotated]
_AUDIO_EMBEDDER = None  # type: ignore[var-annotated]


def _reset_embedder_cache(*, unload: bool = True) -> None:
    """B-554: persistente Embedder freigeben (VRAM) + Cache leeren.

    Wird beim Scheduler-Stop gerufen (VRAM-Hygiene) und von Tests genutzt.
    """
    global _VIDEO_EMBEDDER, _AUDIO_EMBEDDER
    with _EMBEDDER_CACHE_LOCK:
        for emb in (_VIDEO_EMBEDDER, _AUDIO_EMBEDDER):
            if emb is not None and unload:
                try:
                    emb.unload()
                except Exception as exc:  # best-effort — Stop darf nie daran scheitern
                    logger.debug("Embedder-unload fehlgeschlagen (ignoriert): %s", exc)
        _VIDEO_EMBEDDER = None
        _AUDIO_EMBEDDER = None
        if unload:
            logger.info("VRAM-Hygiene: Embedder-Cache (VRAM) erfolgreich freigegeben.")


def _default_embedder_factory(
    task: EmbeddingTask,
    progress_cb: Callable[[float, str], None],
    serializer: GpuSerializer,
):
    """Real-Embedder via Lazy-Import. Wirft ImportError wenn torch fehlt."""
    if task.media_type == "audio":
        from services.brain.audio.audio_embedder import (
            ClapAudioEmbedder,
            CLAP_MODEL_ID,
            CLAP_MODEL_VERSION,
        )
        def _adapted_progress(pct: int, msg: str):
            progress_cb(float(pct / 100.0), msg)

        global _AUDIO_EMBEDDER
        with _EMBEDDER_CACHE_LOCK:
            if _AUDIO_EMBEDDER is None:
                _AUDIO_EMBEDDER = ClapAudioEmbedder(serializer=serializer)
            emb = _AUDIO_EMBEDDER
        result = emb.embed_mix(
            task.source_path,
            audio_hash=task.media_hash,
            progress_cb=_adapted_progress,
        )
        return {
            "embedding": result.mix_embedding,
            "model_name": CLAP_MODEL_ID,
            "model_version": CLAP_MODEL_VERSION,
        }
    elif task.media_type == "video":
        from services.brain.video.video_embedder import (
            Siglip2VideoEmbedder,
            SIGLIP2_MODEL_ID,
            SIGLIP2_MODEL_VERSION,
        )
        global _VIDEO_EMBEDDER
        with _EMBEDDER_CACHE_LOCK:
            if _VIDEO_EMBEDDER is None:
                _VIDEO_EMBEDDER = Siglip2VideoEmbedder(serializer=serializer)
            emb = _VIDEO_EMBEDDER
        result = emb.embed_clip(task.source_path, video_hash=task.media_hash)
        return {
            "embedding": result.clip_embedding,
            "model_name": SIGLIP2_MODEL_ID,
            "model_version": SIGLIP2_MODEL_VERSION,
        }
    else:
        raise ValueError(f"Unbekannter media_type: {task.media_type}")


class EmbeddingScheduler(QObject):
    """Qt-freundlicher Scheduler-Singleton. Singleton via get_default_scheduler()."""

    # B-567: error angehaengt, damit der Fehlertext fehlgeschlagener Jobs bis zur
    # UI durchgereicht wird (vorher stumm). 4-arg-Slots bleiben kompatibel.
    job_progress = Signal(str, str, float, str, str)  # job_id, status, progress, message, error
    job_skipped = Signal(str, str)  # media_hash, reason

    def __init__(
        self,
        n_workers: int = 1,
        cache: Optional[EmbeddingCache] = None,
        embedder_factory: EmbedderFactory = _default_embedder_factory,
        serializer: Optional[GpuSerializer] = None,
    ) -> None:
        super().__init__()
        self.n_workers = n_workers
        self._cache = cache
        self._embedder_factory = embedder_factory
        self._serializer = serializer
        self._thread: Optional[_SchedulerThread] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._thread is not None and self._thread.isRunning():
            return
        cache = self._cache or EmbeddingCache()
        serializer = self._serializer or get_default_serializer()
        self._thread = _SchedulerThread(
            n_workers=self.n_workers,
            cache=cache,
            embedder_factory=self._embedder_factory,
            serializer=serializer,
        )
        self._thread.progress_bridge.connect(self.job_progress)
        self._thread.skipped_bridge.connect(self.job_skipped)
        self._thread.start()
        # B-627: NICHT synchron auf Ready warten (frueher wait_ready(timeout=5.0)
        # -> bis 5s GUI/Boot-Freeze). Der Thread wird gestartet, der Loop wird
        # asynchron bereit. Frueh eintreffende submit_task()-Aufrufe werden im
        # Scheduler-Thread gepuffert und geflusht, sobald der Loop laeuft.
        logger.info("EmbeddingScheduler: gestartet (n_workers=%d)", self.n_workers)

    def request_stop(self, timeout_ms: int = 5000) -> bool:
        if self._thread is None:
            return True
        self._thread.request_stop()
        ok = self._thread.wait(timeout_ms)
        if not ok:
            logger.warning("EmbeddingScheduler: Stop-Timeout %d ms ueberschritten", timeout_ms)
        return ok

    def is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    # ------------------------------------------------------------------
    # B-686: VRAM-Koordination mit dem ModelManager
    # ------------------------------------------------------------------
    def pause_for_analysis(self) -> None:
        """Haelt neue Embeds an UND gibt die residenten Embedder frei, damit
        eine schwere ModelManager-Analyse (SigLIP-so400m + RAFT) VRAM bekommt.

        DEADLOCK-CONSTRAINT: NUR aufrufen, wenn der Caller KEINEN GPU-Lock
        haelt. Der Embedder-Free nimmt via ``emb.unload()`` (B-684) den
        GpuSerializer/GPU_EXECUTION_LOCK. Innerhalb einer gehaltenen
        ``gpu_resource_lease`` (GPU_LOAD_LOCK) waere das die verbotene Kante
        LOAD -> EXECUTION (Gegenkante EXECUTION -> LOAD existiert via
        oom_recovery -> Deadlock). Am ``run()``-Start des Analyse-Workers ist
        noch keine Lease genommen -> sicher.
        """
        thread = self._thread
        if thread is not None:
            thread.pause_embeddings()
        # Free residenter Embedder (beide: SigLIP-2 + CLAP) ausserhalb jeder Lease.
        try:
            _reset_embedder_cache(unload=True)
        except Exception as exc:  # best-effort — Analyse darf nie daran scheitern
            logger.warning("B-686 pause_for_analysis: Embedder-Free fehlgeschlagen: %s", exc)

    def resume_after_analysis(self) -> None:
        """Hebt die Embed-Pause auf. Der naechste Job laedt die Embedder lazy neu."""
        thread = self._thread
        if thread is not None:
            thread.resume_embeddings()

    # ------------------------------------------------------------------
    # Submit
    # ------------------------------------------------------------------
    def submit_path(
        self,
        media_hash: str,
        source_path: Path | str,
        media_type: str,
    ) -> Optional[str]:
        """Schickt Embedding-Task in die Queue. Liefert job_id oder None bei Cache-Hit.

        Cache-Check passiert hier (synchron, schnell). Bei Hit: Signal `job_skipped`
        + return None. Bei Miss: Job in EmbeddingJobQueue.
        """
        if self._thread is None or not self._thread.isRunning():
            raise RuntimeError("EmbeddingScheduler ist nicht gestartet.")
        task = EmbeddingTask(
            media_hash=media_hash,
            media_type=media_type,
            source_path=Path(source_path),
        )
        return self._thread.submit_task(task)


# ----------------------------------------------------------------------
# Internals
# ----------------------------------------------------------------------
class _SchedulerThread(QThread):
    """QThread mit eigenem asyncio-Loop, hostet EmbeddingJobQueue."""

    progress_bridge = Signal(str, str, float, str, str)  # B-567: +error
    skipped_bridge = Signal(str, str)

    def __init__(
        self,
        *,
        n_workers: int,
        cache: EmbeddingCache,
        embedder_factory: EmbedderFactory,
        serializer: GpuSerializer,
    ) -> None:
        super().__init__()
        self._n_workers = n_workers
        self._cache = cache
        self._embedder_factory = embedder_factory
        self._serializer = serializer
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._queue: Optional[EmbeddingJobQueue] = None
        self._ready_event = threading.Event()
        self._stop_event = threading.Event()
        # B-686: Pause-Gate — gesetzt = neue Embeds warten (VRAM-Koordination
        # waehrend schwerer ModelManager-Analyse). Cross-thread via Event.
        # Refcount, weil MEHRERE Analyse-Worker gleichzeitig laufen koennen
        # (Batch + Pipeline, 2 Pipeline-Entry-Points): das Gate darf erst
        # aufgehen, wenn ALLE resume gerufen haben — sonst laedt ein Embed die
        # Embedder neu resident, waehrend ein zweiter Worker noch analysiert
        # (reproduziert genau den OOM, den B-686 verhindert). P1-Skeptic-Fund.
        self._pause_event = threading.Event()
        self._pause_count = 0
        self._pause_lock = threading.Lock()
        # B-627: Puffer fuer submit_task-Aufrufe, die eintreffen bevor der Loop
        # bereit ist (early submit vor Boot-Ready). Geflusht in run(), sobald der
        # Loop laeuft. _pending_lock serialisiert Ready-Wechsel + Puffer-Zugriff.
        self._pending_lock = threading.Lock()
        self._pending: list[tuple[str, EmbeddingTask]] = []
        self._ready = False

    def wait_ready(self, timeout: float = 5.0) -> bool:
        return self._ready_event.wait(timeout=timeout)

    def request_stop(self) -> None:
        self._stop_event.set()
        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

    # B-686: Pause-Gate ----------------------------------------------------
    def pause_embeddings(self) -> None:
        with self._pause_lock:
            self._pause_count += 1
            self._pause_event.set()

    def resume_embeddings(self) -> None:
        with self._pause_lock:
            if self._pause_count > 0:
                self._pause_count -= 1
            # Gate erst aufmachen, wenn KEIN Analyse-Worker mehr pausiert.
            if self._pause_count == 0:
                self._pause_event.clear()

    async def _await_gate(self) -> bool:
        """B-686: Blockiert (async, ohne GPU-Lock) solange pausiert. Liefert
        ``True`` = weitermachen, ``False`` = Stop angefordert (Vorrang)."""
        while self._pause_event.is_set() and not self._stop_event.is_set():
            await asyncio.sleep(0.1)
        return not self._stop_event.is_set()

    def submit_task(self, task: EmbeddingTask) -> Optional[str]:
        # B-627: job_id vorab auf dem Aufrufer-Thread (GUI) generieren, damit die
        # Einreichung NICHT synchron auf den Scheduler-Loop warten muss (frueher
        # future.result(timeout=5.0) -> bis 5s GUI-Freeze beim Import).
        job_id = uuid.uuid4().hex[:12]
        with self._pending_lock:
            loop = self._loop
            if not self._ready or loop is None or not loop.is_running():
                if self._stop_event.is_set():
                    # Explizit gestoppt -> keine neuen Jobs annehmen (wie bisher).
                    raise RuntimeError("Scheduler-Loop ist nicht aktiv.")
                # Loop noch nicht bereit (early submit vor Boot-Ready): puffern
                # statt zu crashen. run() flusht den Puffer, sobald der Loop laeuft.
                self._pending.append((job_id, task))
                return job_id
        # Loop laeuft -> fire-and-forget einreihen, NICHT auf das Ergebnis warten.
        self._schedule_job(loop, job_id, task)
        return job_id

    def _schedule_job(
        self, loop: asyncio.AbstractEventLoop, job_id: str, task: EmbeddingTask
    ) -> None:
        """Reiht die Job-Coroutine thread-safe in den laufenden Loop ein (fire-and-forget)."""
        future = asyncio.run_coroutine_threadsafe(
            self._build_and_submit_job(task, job_id),
            loop,
        )
        future.add_done_callback(self._on_submit_done)

    def _on_submit_done(self, future) -> None:
        """B-627: Einreih-Fehler nicht stumm verschlucken (frueher via .result())."""
        try:
            exc = future.exception()
        except Exception:  # CancelledError / InvalidState — ignorieren
            return
        if exc is not None:
            logger.warning(
                "EmbeddingScheduler: Job-Einreichung in Queue fehlgeschlagen: %s", exc
            )

    async def _build_and_submit_job(self, task: EmbeddingTask, job_id: str) -> str:
        async def _run(progress_cb):
            return await self._execute_embedding(task, progress_cb)

        job = EmbeddingJob(
            label=f"{task.media_type.upper()}: {task.source_path.name}",
            run=_run,
            job_id=job_id,
        )
        submitted_id = await self._queue.submit(job)
        return submitted_id

    async def _execute_embedding(
        self,
        task: EmbeddingTask,
        progress_cb: Callable[[float, str], None],
    ):
        import numpy as np
        progress_cb(0.05, "starting")
        # B-686: Pause-Gate VOR dem Executor-Dispatch — waehrend einer schweren
        # ModelManager-Analyse wartet der Job hier, statt den Embedder (VRAM)
        # neu resident zu machen. Das Warten haelt KEINEN GPU-Lock -> keine
        # Lock-Inversion. Stop hat Vorrang (bricht das Warten ab).
        if not await self._await_gate():
            progress_cb(1.0, "paused-stop")
            return None
        loop = asyncio.get_running_loop()

        def _blocking_embed():
            from services.brain.video.video_embedder import InvalidVideoError
            try:
                return self._embedder_factory(task, progress_cb, self._serializer)
            except (InvalidVideoError, OSError, IOError) as exc:
                raise SkipEmbeddingError(str(exc)) from exc

        try:
            payload = await loop.run_in_executor(None, _blocking_embed)
        except SkipEmbeddingError as exc:
            logger.info(
                "Embedding-Skip (Medium unlesbar oder ungueltig) hash=%s: %s",
                task.media_hash, exc,
            )
            self.skipped_bridge.emit(task.media_hash, str(exc))
            progress_cb(1.0, f"skipped ({str(exc)})")
            return None

        def _blocking_store(payload_data):
            embedding = payload_data["embedding"]
            model_name = payload_data["model_name"]
            model_version = payload_data["model_version"]
            if not isinstance(embedding, np.ndarray):
                raise TypeError(
                    f"embedder lieferte kein numpy.ndarray, war: {type(embedding)}"
                )
            entry = self._cache.store(
                media_hash=task.media_hash,
                media_type=task.media_type,
                embedding=embedding,
                model_name=model_name,
                model_version=model_version,
            )
            return {
                "media_hash": task.media_hash,
                "embedding_path": str(entry.embedding_path),
                "model_name": model_name,
                "model_version": model_version,
            }

        result = await loop.run_in_executor(None, _blocking_store, payload)
        progress_cb(1.0, "stored")
        return result

    def _bridge_progress(self, progress: JobProgress) -> None:
        self.progress_bridge.emit(
            progress.job_id,
            progress.status.value,
            progress.progress,
            progress.message or "",
            progress.error or "",  # B-567: Fehlertext mitliefern (vorher verworfen)
        )
        # B-VRAM-HYGIENE: Wenn der Job beendet ist, pruefe ob die Queue leer ist
        from services.brain.background_queue import JobStatus
        if progress.status in (JobStatus.DONE, JobStatus.FAILED, JobStatus.CANCELLED):
            if self._queue is not None:
                all_jobs = self._queue.all_progress().values()
                active_count = sum(1 for j in all_jobs if j.status in (JobStatus.PENDING, JobStatus.RUNNING))
                if active_count == 0:
                    logger.info("VRAM-Hygiene: Alle Jobs erledigt. Entlade Embedder-Cache (VRAM freigeben)...")
                    try:
                        _reset_embedder_cache(unload=True)
                    except Exception as exc:
                        logger.warning("Automatisches VRAM-Entladen fehlgeschlagen: %s", exc)

    def run(self) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._queue = EmbeddingJobQueue(n_workers=self._n_workers)
        self._queue.subscribe(self._bridge_progress)

        async def _bootstrap() -> None:
            # Inside the running loop: asyncio.create_task ist erlaubt.
            self._queue.start()

        def _mark_ready_and_flush() -> None:
            # Laeuft INNERHALB des laufenden Loops (loop.is_running() == True),
            # daher koennen gepufferte Early-Submits sicher eingereiht werden.
            # B-627: Wurde bereits ein Stop angefordert BEVOR der Loop lief
            # (request_stop() traf ein waehrend loop.is_running()==False, sein
            # loop.stop() verpuffte), hier sofort stoppen statt run_forever
            # endlos laufen zu lassen.
            if self._stop_event.is_set():
                loop.stop()
                return
            with self._pending_lock:
                self._ready = True
                pending = self._pending
                self._pending = []
            self._ready_event.set()
            for job_id, task in pending:
                fut = asyncio.ensure_future(
                    self._build_and_submit_job(task, job_id)
                )
                fut.add_done_callback(self._on_submit_done)

        try:
            loop.run_until_complete(_bootstrap())
            # B-627: Ready-Flag + Puffer-Flush erst setzen, wenn der Loop laeuft.
            loop.call_soon(_mark_ready_and_flush)
            loop.run_forever()
        finally:
            try:
                loop.run_until_complete(self._queue.stop(drain=True))
            except Exception as exc:
                logger.warning("EmbeddingScheduler: stop-drain Fehler: %s", exc)
            loop.close()
            self._loop = None
            self._queue = None
            # B-554: persistente Embedder beim Scheduler-Stop freigeben (VRAM).
            _reset_embedder_cache(unload=True)


# --- Modul-globaler Default-Scheduler ----------------------------------
_DEFAULT: Optional[EmbeddingScheduler] = None
_default_lock = threading.Lock()


def get_default_scheduler() -> EmbeddingScheduler:
    global _DEFAULT
    if _DEFAULT is None:
        with _default_lock:
            if _DEFAULT is None:
                _DEFAULT = EmbeddingScheduler()
    return _DEFAULT


def reset_default_scheduler_for_tests() -> None:
    global _DEFAULT
    with _default_lock:
        if _DEFAULT is not None:
            try:
                _DEFAULT.request_stop()
            except Exception:
                pass
        _DEFAULT = None
