"""Cached GPU-/CUDA-Info fuer alle Main-Thread Konsumenten.

Hintergrund: `torch.cuda.is_available()` / `get_device_name()` /
`memory_allocated()` blockieren den Aufrufer unbekannt lange, wenn der
CUDA-Treiber in einem Stuck-State ist (bekannt nach Prozess-Kill waehrend
CUDA-Workload). Deshalb darf KEINE GUI-Klickbahn (Dialog-Open, Tooltip,
Status-Label) direkt torch.cuda.* aufrufen.

Dieses Modul stellt einen Snapshot bereit, der beim App-Boot EINMAL
synchron befuellt wird (dort ist eine Verzoegerung akzeptabel) und danach
aus allen Slots/paint-Methoden lockfrei gelesen werden kann.

Usage:
    # Einmal beim Boot (main.py):
    from services.gpu_info import initialize_gpu_info_cache
    initialize_gpu_info_cache()

    # Jeder weitere Zugriff:
    from services.gpu_info import get_gpu_info
    info = get_gpu_info()
    info.available, info.name, info.cuda_version, info.total_mb

VRAM-Live-Messung (memory_allocated) ist seperat:
    try_memory_allocated(device=0) -> int | None  # None bei Fehler/Timeout
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class GPUInfo:
    available: bool
    name: str
    cuda_version: str
    total_mb: float
    compiled_cuda: str
    error: str = ""

    def summary(self) -> str:
        if self.available:
            return f"{self.name}  |  CUDA {self.cuda_version}"
        if self.error:
            return f"Keine CUDA-GPU ({self.error})"
        return "Keine CUDA-GPU erkannt"


_cache: GPUInfo | None = None
_lock = threading.Lock()


def initialize_gpu_info_cache(force: bool = False) -> GPUInfo:
    """Synchron befuellen. Beim Boot aus main.py aufrufen.

    Wenn force=True, wird neu ermittelt (nuetzlich nach GPU-Reset).
    """
    global _cache
    with _lock:
        if _cache is not None and not force:
            return _cache
        try:
            import torch  # type: ignore
            compiled = getattr(torch.version, "cuda", "") or ""
            if torch.cuda.is_available():
                _cache = GPUInfo(
                    available=True,
                    name=torch.cuda.get_device_name(0),
                    cuda_version=torch.version.cuda or "n/a",
                    total_mb=torch.cuda.get_device_properties(0).total_memory / (1024 * 1024),
                    compiled_cuda=compiled,
                )
            else:
                _cache = GPUInfo(
                    available=False,
                    name="",
                    cuda_version="",
                    total_mb=0.0,
                    compiled_cuda=compiled,
                    error="torch.cuda.is_available() = False",
                )
        except Exception as exc:  # Defensiv — Init darf Boot nie blockieren
            logger.warning("initialize_gpu_info_cache: %s", exc)
            _cache = GPUInfo(
                available=False, name="", cuda_version="", total_mb=0.0,
                compiled_cuda="", error=str(exc)[:100],
            )
    return _cache


def get_gpu_info() -> GPUInfo:
    """Liefert den Cache. Falls noch nicht initialisiert, liefert neutralen
    Not-Available-Wert statt zu blocken."""
    if _cache is None:
        return GPUInfo(available=False, name="", cuda_version="", total_mb=0.0,
                       compiled_cuda="", error="cache not initialized")
    return _cache


def try_memory_allocated(device: int = 0) -> float | None:
    """Live VRAM-Messung mit Schutz vor Stuck-Driver.

    Fuer ResourceMonitor (Worker-Thread). Gibt None zurueck bei Fehler —
    Caller muss das abfangen. KEIN Main-Thread-Aufruf empfohlen.
    """
    if _cache is None or not _cache.available:
        return None
    try:
        import torch  # type: ignore
        return torch.cuda.memory_allocated(device) / (1024 * 1024)
    except Exception as exc:
        logger.debug("try_memory_allocated failed: %s", exc)
        return None


def detect_stuck_driver() -> tuple[bool, str]:
    """Erkennt, ob der CUDA-Driver im "stuck" Zustand ist.

    Typisches Symptom nach hartem Kill eines CUDA-Workloads:
      - torch.cuda.is_available() = False
      - Unmittelbar nach Treiber-Install/Reset waere True erwartet
      - Error-Msg enthaelt "CUDA unknown error" oder "CUDA initialization"

    Returns:
        (is_stuck, error_message)
    """
    try:
        import torch  # type: ignore
    except Exception as exc:
        return False, f"torch import failed: {exc}"

    # Wenn kein CUDA-compiled, kein Stuck-Zustand — ist einfach CPU-only
    if not getattr(torch.version, "cuda", ""):
        return False, "torch ohne CUDA kompiliert"

    # Forcieren eines frischen Init-Versuchs. Wenn der Treiber stuck ist,
    # wirft torch hier typischerweise einen "CUDA unknown error" UserWarning
    # und gibt False zurueck.
    import warnings
    captured = []
    with warnings.catch_warnings(record=True) as ws:
        warnings.simplefilter("always")
        try:
            available = bool(torch.cuda.is_available())
        except Exception as exc:
            return True, f"is_available() raised: {exc}"
        for w in ws:
            msg = str(w.message)
            if "CUDA" in msg and ("unknown error" in msg or "initialization" in msg):
                captured.append(msg)

    if available:
        return False, "OK"
    if captured:
        return True, captured[0][:200]
    # CUDA compiled aber nicht verfuegbar — koennte auch fehlender Treiber sein,
    # das ist dann NICHT stuck. Wir geben False zurueck damit der User nicht
    # einen Recovery-Prompt bekommt, wenn er einfach keine NVIDIA-GPU hat.
    return False, "torch.cuda.is_available() = False (kein Treiber-Fehler erkannt)"


def run_recovery_script() -> bool:
    """Startet scripts/cuda_recovery.ps1 via UAC-Elevation.

    Gibt True zurueck wenn der Subprozess sauber gestartet wurde (der User
    muss den UAC-Dialog bestaetigen; der Erfolg der Recovery ist damit nicht
    garantiert).
    """
    import subprocess
    from pathlib import Path
    script = Path(__file__).resolve().parent.parent / "scripts" / "cuda_recovery.ps1"
    if not script.exists():
        logger.warning("cuda_recovery.ps1 nicht gefunden: %s", script)
        return False
    try:
        subprocess.Popen(
            ["powershell.exe", "-ExecutionPolicy", "Bypass", "-File", str(script)],
            creationflags=0x00000008 if hasattr(subprocess, "DETACHED_PROCESS") else 0,  # DETACHED_PROCESS
        )
        return True
    except Exception as exc:
        logger.warning("cuda_recovery.ps1 start failed: %s", exc)
        return False
