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
import os
import sys
import threading
import time
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

logger = logging.getLogger(__name__)

# B-503: sync acquire() bekommt einen Timeout (default 300 s) statt unendlich
# zu blockieren (non-reentranter self._lock → Self-Deadlock bei Verschachtelung
# war vorher unentdeckbar). Ab 30 s Wartezeit wird der aktuelle Holder geloggt.
DEFAULT_ACQUIRE_TIMEOUT_S = 300.0
_WAIT_LOG_INTERVAL_S = 30.0

# B-804: der Warte-Pfad war abgesichert (B-503), der HALTE-Pfad nicht. Ein
# Holder, der nie zurueckkommt (haengender ffmpeg-Reader, toter Worker-Thread,
# blockierter GUI-Thread), haelt den Lock unbegrenzt — beim Vorfall vom
# 2026-08-11 27 Minuten lang, ohne eine einzige Logzeile. Der Hold-Watchdog
# meldet einen ueberfaelligen Halter und dumpt die Stacks ALLER Threads in
# eine eigene Datei; er greift bewusst NICHT ein (kein Force-Release, kein
# Raise) — die B-503-Timeout-Semantik der Warteseite bleibt unveraendert.
DEFAULT_HOLD_WARN_S = 300.0
_HOLD_POLL_INTERVAL_S = 5.0
_STALL_DUMP_ENV = "PB_GPU_STALL_DUMP"
_HOLD_WARN_ENV = "PB_GPU_HOLD_WARN_S"


def _default_stall_dump_path() -> Path:
    """Ablageort fuer den Stall-Stackdump (eigene Datei, kein Mischschreiber).

    Bewusst NICHT ``logs/freeze_stacks.log``: dort haelt ``main.py`` einen
    eigenen offenen ``faulthandler``-Handle; zwei Schreiber auf demselben
    File wuerden sich die Eintraege zerschneiden.
    """
    override = os.environ.get(_STALL_DUMP_ENV, "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "logs" / "gpu_serializer_stalls.log"


def _env_hold_warn_s(default: float = DEFAULT_HOLD_WARN_S) -> float:
    raw = os.environ.get(_HOLD_WARN_ENV, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return value if value > 0 else default


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

    def __init__(
        self,
        *,
        name: str = "brain_v3",
        empty_cache_on_release: bool = True,
        hold_warn_s: Optional[float] = None,
        hold_poll_s: float = _HOLD_POLL_INTERVAL_S,
    ):
        self.name = name
        self.empty_cache_on_release = empty_cache_on_release
        self._lock = threading.Lock()
        self._async_lock: Optional[asyncio.Lock] = None  # lazy
        self._current_holder: Optional[str] = None
        # B-804: Hold-Watchdog-Zustand.
        self._hold_warn_s = _env_hold_warn_s() if hold_warn_s is None else float(hold_warn_s)
        self._hold_poll_s = max(0.01, float(hold_poll_s))
        self._hold_started_at: Optional[float] = None
        self._hold_thread: Optional[str] = None
        self._hold_watchdog: Optional[threading.Thread] = None
        self._hold_watchdog_lock = threading.Lock()
        self.stall_reports: int = 0

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
        prev_started = self._hold_started_at
        prev_thread = self._hold_thread
        self._current_holder = holder
        # B-804: Halte-Beginn markieren + Watchdog scharfschalten.
        self._hold_started_at = time.monotonic()
        self._hold_thread = threading.current_thread().name
        self._ensure_hold_watchdog()
        logger.debug("GpuSerializer[%s].acquired by %s", self.name, holder)
        try:
            yield
        finally:
            if self.empty_cache_on_release:
                self._try_empty_cuda_cache()
            self._current_holder = prev
            self._hold_started_at = prev_started
            self._hold_thread = prev_thread
            self._lock.release()
            legacy_lock.release()
            logger.debug("GpuSerializer[%s].released by %s", self.name, holder)

    # --- B-804: Hold-Watchdog -------------------------------------------
    def _ensure_hold_watchdog(self) -> None:
        """Startet den Beobachter-Thread beim ersten Acquire (lazy, daemon)."""
        if self._hold_watchdog is not None:
            return
        with self._hold_watchdog_lock:
            if self._hold_watchdog is not None:
                return
            thread = threading.Thread(
                target=self._hold_watchdog_loop,
                name=f"gpu-hold-watchdog-{self.name}",
                daemon=True,
            )
            self._hold_watchdog = thread
            thread.start()

    def _hold_watchdog_loop(self) -> None:
        last_report = 0.0
        while True:
            time.sleep(self._hold_poll_s)
            started = self._hold_started_at
            if started is None:
                last_report = 0.0
                continue
            held = time.monotonic() - started
            if held < self._hold_warn_s:
                continue
            now = time.monotonic()
            if last_report and (now - last_report) < self._hold_warn_s:
                continue
            last_report = now
            try:
                self._report_stalled_holder(held)
            except Exception as exc:  # pragma: no cover - Watchdog darf nie sterben
                logger.debug("GpuSerializer hold-watchdog report failed: %s", exc)

    def _report_stalled_holder(self, held_s: float) -> None:
        """Meldet einen ueberfaelligen Halter und dumpt alle Thread-Stacks.

        Greift NICHT ein: der Lock bleibt gehalten, es fliegt keine Exception.
        Der Dump geht zusaetzlich in eine Datei, weil beim Vorfall vom
        2026-08-11 auch die Logging-Kette stumm war — ein reiner
        ``logger.error`` waere dort verlorengegangen.
        """
        holder = self._current_holder
        thread_name = self._hold_thread
        logger.error(
            "GpuSerializer[%s]: Halter %r (Thread %r) haelt den Lock seit %.1fs "
            "(Schwelle %.1fs) — Stack-Dump: %s",
            self.name, holder, thread_name, held_s, self._hold_warn_s,
            self._stall_dump_path,
        )
        try:
            dump = self._format_all_thread_stacks()
        except Exception as exc:  # broad: Diagnose darf nie ganz ausfallen
            dump = f"(Stack-Dump fehlgeschlagen: {exc!r})\n"
        header = (
            f"\n=== GPU-SERIALIZER STALL [{self.name}] "
            f"holder={holder!r} thread={thread_name!r} "
            f"held={held_s:.1f}s threshold={self._hold_warn_s:.1f}s "
            f"ts={time.strftime('%Y-%m-%d %H:%M:%S')} ===\n"
        )
        path = self._stall_dump_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fp:
                fp.write(header)
                fp.write(dump)
                fp.flush()
        except OSError as exc:
            logger.error("GpuSerializer[%s]: Stall-Dump nach %s fehlgeschlagen: %s",
                         self.name, path, exc)
        # Zaehler zuletzt: 'stall_reports' bedeutet "Meldung inkl. Dump fertig".
        self.stall_reports += 1

    @property
    def _stall_dump_path(self) -> Path:
        return _default_stall_dump_path()

    @staticmethod
    def _format_all_thread_stacks() -> str:
        names = {t.ident: t.name for t in threading.enumerate()}
        chunks = []
        # Snapshot: das Dict von sys._current_frames() darf sich waehrend der
        # Iteration aendern (RuntimeError) — deshalb erst kopieren.
        for ident, frame in list(sys._current_frames().items()):
            chunks.append(f"\n--- Thread {names.get(ident, '?')} (id={ident}) ---\n")
            chunks.append("".join(traceback.format_stack(frame)))
        return "".join(chunks)

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
