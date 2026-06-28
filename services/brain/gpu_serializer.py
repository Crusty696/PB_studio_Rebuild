"""Brain V3 — GPU-Serializer fuer CLAP / SigLIP-2 Singletons.

Plan-Doc 02 #21+#23: alle V3-GPU-Workloads durch einen Serial-Lock,
damit CLAP, SigLIP-2, (spaeter) Demucs/RAFT/NVENC nicht gleichzeitig
um VRAM kaempfen.

Spike 2026-05-03 hat gezeigt:
- CLAP + SigLIP-2 koexistent ist VRAM-maeszig moeglich (1178 MB reserved
  von 6 GB), sequenzieller Lifecycle ist also "Empfohlen", nicht "Pflicht"
- Aber: zusammen mit Demucs/RAFT/NVENC kann es kippen → Lock bleibt
  als Defensive

Implementation: threading.Lock (sync) + Async-Wrapper fuer asyncio-Konsumenten.
Kein globales Singleton — jede Instanz haelt ihren eigenen Lock; in der
App-Schicht wird ein Modul-globales Singleton erzeugt (siehe get_default_serializer).
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import threading
import time
from contextlib import contextmanager
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

# B-503: sync acquire() bekommt einen Timeout (default 300 s) statt unendlich
# zu blockieren (non-reentranter self._lock → Self-Deadlock bei Verschachtelung
# war vorher unentdeckbar). Ab 30 s Wartezeit wird der aktuelle Holder geloggt.
DEFAULT_ACQUIRE_TIMEOUT_S = 300.0
_WAIT_LOG_INTERVAL_S = 30.0


class GpuSerializer:
    """Thread-sicherer Serial-Lock fuer GPU-Workloads.

    Usage (sync):
        with serializer.acquire("clap_embed"):
            features = clap_model(...)

    Usage (async):
        async with serializer.acquire_async("clap_embed"):
            features = await embed_async(...)

    Optional: cuda.empty_cache() automatisch beim Release ausfuehren
    (empty_cache_on_release=True).
    """

    def __init__(self, *, name: str = "brain_v3", empty_cache_on_release: bool = True):
        self.name = name
        self.empty_cache_on_release = empty_cache_on_release
        self._lock = threading.Lock()
        self._async_lock: Optional[asyncio.Lock] = None  # lazy
        self._current_holder: Optional[str] = None

    @contextmanager
    def acquire(
        self,
        holder: str = "anonymous",
        timeout: Optional[float] = DEFAULT_ACQUIRE_TIMEOUT_S,
    ) -> Iterator[None]:
        """Sync-Variante. Gibt nichts zurueck — Lock wird ueber Context geschuetzt.

        B-503: ``timeout`` (Sekunden, default 300, ``None`` = unendlich) begrenzt
        die Gesamt-Wartezeit auf legacy GPU_EXECUTION_LOCK + internen Lock.
        Bei Wartezeit > 30 s wird der aktuelle Holder geloggt; bei Timeout
        fliegt ``TimeoutError`` mit Holder-Info statt stillem Ewig-Block
        (z.B. Self-Deadlock durch verschachteltes acquire im selben Thread).
        """
        logger.debug("GpuSerializer[%s].acquire(%s) waiting", self.name, holder)
        deadline = None if timeout is None else time.monotonic() + timeout
        # Bridge-Verhalten unveraendert (B-503): erst legacy GPU_EXECUTION_LOCK
        # (RLock, reentrant), dann der eigene non-reentrante Serializer-Lock.
        legacy_lock = self._legacy_gpu_execution_lock()
        if not self._timed_acquire(legacy_lock, "GPU_EXECUTION_LOCK(legacy)", holder, deadline):
            raise TimeoutError(
                f"GpuSerializer[{self.name}]: '{holder}' Timeout ({timeout}s) beim Warten "
                f"auf GPU_EXECUTION_LOCK(legacy) — aktueller Serializer-Holder: "
                f"{self._current_holder!r}"
            )
        try:
            if not self._timed_acquire(self._lock, "serializer-lock", holder, deadline):
                raise TimeoutError(
                    f"GpuSerializer[{self.name}]: '{holder}' Timeout ({timeout}s) beim Warten "
                    f"auf serializer-lock — aktueller Holder: {self._current_holder!r}"
                )
        except BaseException:
            legacy_lock.release()
            raise
        prev = self._current_holder
        self._current_holder = holder
        logger.debug("GpuSerializer[%s].acquired by %s", self.name, holder)
        try:
            yield
        finally:
            if self.empty_cache_on_release:
                self._try_empty_cuda_cache()
            self._current_holder = prev
            self._lock.release()
            legacy_lock.release()
            logger.debug("GpuSerializer[%s].released by %s", self.name, holder)

    def _timed_acquire(self, lock, label: str, holder: str, deadline: Optional[float]) -> bool:
        """B-503: Lock-Acquire mit Deadline + Holder-Logging bei langer Wartezeit.

        Returns ``True`` wenn der Lock gehalten wird, ``False`` bei Timeout.
        Mock-Locks ohne ``timeout``-Support fallen auf blocking acquire zurueck.
        """
        start = time.monotonic()
        while True:
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                return False
            slice_s = (
                _WAIT_LOG_INTERVAL_S
                if remaining is None
                else min(_WAIT_LOG_INTERVAL_S, remaining)
            )
            try:
                acquired = lock.acquire(timeout=slice_s)
            except TypeError:
                # Test-Doubles ohne timeout-Parameter — blocking acquire wie vorher.
                lock.acquire()
                acquired = True
            if acquired:
                return True
            logger.warning(
                "GpuSerializer[%s]: '%s' wartet seit %.0fs auf %s (aktueller Holder: %r)",
                self.name, holder, time.monotonic() - start, label, self._current_holder,
            )

    def acquire_async(self, holder: str = "anonymous"):
        """Async-Variante — lazy-init asyncio.Lock im Event-Loop."""
        if self._async_lock is None:
            self._async_lock = asyncio.Lock()
        return _AsyncAcquireCtx(self, holder)

    def is_locked(self) -> bool:
        return self._lock.locked()

    def current_holder(self) -> Optional[str]:
        return self._current_holder

    @staticmethod
    def _try_empty_cuda_cache() -> None:
        """Best-effort cuda.empty_cache() — Fehler werden geloggt aber nicht eskaliert."""
        try:
            import torch  # type: ignore
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception as exc:
            logger.debug("empty_cache failed (ignored): %s", exc)

    @staticmethod
    def _legacy_gpu_execution_lock():
        """Bridge zu V1/V2 GPU lock, damit Brain V3 mit Demucs/RAFT serialisiert."""
        from services.model_manager import GPU_EXECUTION_LOCK
        return GPU_EXECUTION_LOCK


class _AsyncAcquireCtx:
    """Async-Context-Manager fuer GpuSerializer.acquire_async().

    B-503: Blocking Lock-Acquires laufen via ``loop.run_in_executor`` in einem
    dedizierten Single-Thread-Executor statt synchron in der Coroutine — vorher
    blockierte ``__aenter__`` den gesamten Event-Loop solange ein anderer
    Thread den GPU-Lock hielt. Der Single-Thread-Executor ist Pflicht, weil
    der legacy GPU_EXECUTION_LOCK ein ``threading.RLock`` ist (thread-affin):
    acquire und release MUESSEN im selben Thread passieren.

    Hinweis: Dadurch greift die RLock-Reentranz des Event-Loop-Threads fuer
    den legacy Lock nicht mehr (Acquire laeuft im Executor-Thread). Der
    Async-Pfad wird aktuell nur in Tests genutzt; Konsumenten duerfen
    ``acquire_async`` nicht aufrufen waehrend derselbe Thread den
    GPU_EXECUTION_LOCK bereits haelt.
    """

    def __init__(self, serializer: GpuSerializer, holder: str):
        self._s = serializer
        self._holder = holder
        self._prev: Optional[str] = None
        self._legacy_lock = None
        self._executor: Optional[concurrent.futures.ThreadPoolExecutor] = None

    async def __aenter__(self):
        assert self._s._async_lock is not None
        loop = asyncio.get_running_loop()
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=1, thread_name_prefix=f"gpu_ser_async_{self._s.name}",
        )
        self._legacy_lock = self._s._legacy_gpu_execution_lock()
        try:
            await loop.run_in_executor(self._executor, self._legacy_lock.acquire)
        except BaseException:
            self._cleanup_executor()
            self._legacy_lock = None
            raise
        try:
            await self._s._async_lock.acquire()
            # Auch sync-Lock greifen — dieselbe Resource wird ggf. von
            # sync-Konsumenten genutzt. threading.Lock darf von beliebigen
            # Threads released werden — Executor-Acquire ist hier unkritisch.
            await loop.run_in_executor(self._executor, self._s._lock.acquire)
            self._prev = self._s._current_holder
            self._s._current_holder = self._holder
            return None
        except BaseException:
            # Legacy-RLock im selben Executor-Thread releasen (thread-affin).
            self._executor.submit(self._legacy_lock.release).result()
            self._cleanup_executor()
            self._legacy_lock = None
            raise

    async def __aexit__(self, exc_type, exc, tb):
        if self._s.empty_cache_on_release:
            self._s._try_empty_cuda_cache()
        self._s._current_holder = self._prev
        self._s._lock.release()
        assert self._s._async_lock is not None
        self._s._async_lock.release()
        assert self._legacy_lock is not None
        assert self._executor is not None
        loop = asyncio.get_running_loop()
        # Release im selben Executor-Thread wie das Acquire (RLock thread-affin).
        await loop.run_in_executor(self._executor, self._legacy_lock.release)
        self._cleanup_executor()
        self._legacy_lock = None
        return False  # don't suppress

    def _cleanup_executor(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=False)
            self._executor = None


# --- Modul-globaler Default-Serializer (lazy) -------------------------------
_DEFAULT: Optional[GpuSerializer] = None
_default_lock = threading.Lock()


def get_default_serializer() -> GpuSerializer:
    """Singleton fuer den App-weiten Default-Serializer."""
    global _DEFAULT
    if _DEFAULT is None:
        with _default_lock:
            if _DEFAULT is None:
                _DEFAULT = GpuSerializer(name="brain_v3_default")
    return _DEFAULT


def reset_default_serializer_for_tests() -> None:
    """Test-Helper — resettet das Modul-globale Singleton."""
    global _DEFAULT
    with _default_lock:
        _DEFAULT = None
