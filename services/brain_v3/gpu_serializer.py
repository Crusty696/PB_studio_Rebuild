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
import logging
import threading
from contextlib import contextmanager
from typing import Iterator, Optional

logger = logging.getLogger(__name__)


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
    def acquire(self, holder: str = "anonymous") -> Iterator[None]:
        """Sync-Variante. Gibt nichts zurueck — Lock wird ueber Context geschuetzt."""
        logger.debug("GpuSerializer[%s].acquire(%s) waiting", self.name, holder)
        legacy_lock = self._legacy_gpu_execution_lock()
        legacy_lock.acquire()
        self._lock.acquire()
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
    """Async-Context-Manager fuer GpuSerializer.acquire_async()."""

    def __init__(self, serializer: GpuSerializer, holder: str):
        self._s = serializer
        self._holder = holder
        self._prev: Optional[str] = None
        self._legacy_lock = None

    async def __aenter__(self):
        assert self._s._async_lock is not None
        self._legacy_lock = self._s._legacy_gpu_execution_lock()
        self._legacy_lock.acquire()
        try:
            await self._s._async_lock.acquire()
            # Auch sync-Lock greifen — dieselbe Resource wird ggf. von sync-Konsumenten genutzt
            self._s._lock.acquire()
            self._prev = self._s._current_holder
            self._s._current_holder = self._holder
            return None
        except BaseException:
            self._legacy_lock.release()
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
        self._legacy_lock.release()
        self._legacy_lock = None
        return False  # don't suppress


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
