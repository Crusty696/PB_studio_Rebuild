"""Startup dependency checker for PB Studio.

Runs three checks in parallel (ThreadPoolExecutor) to stay under 2s:
  1. FFmpeg / FFprobe — binary existence + version string
  2. CUDA / GPU       — torch.cuda lazy-import, name + VRAM
  3. Disk space       — shutil.disk_usage on APP_ROOT
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_FFMPEG_BIN = os.environ.get("FFMPEG_PATH", "ffmpeg")
_FFPROBE_BIN = os.environ.get("FFPROBE_PATH", "ffprobe")
_MIN_DISK_BYTES = 1 * 1024 ** 3  # 1 GiB


@dataclass
class SystemStatus:
    ffmpeg_ok: bool = False
    ffmpeg_version: str = ""
    ffprobe_ok: bool = False
    cuda_ok: bool = False
    gpu_name: str = ""
    gpu_vram_mb: int = 0
    disk_free_gb: float = 0.0
    disk_ok: bool = False
    ollama_ok: bool = False
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def status_bar_text(self) -> str:
        parts: list[str] = []
        if self.cuda_ok and self.gpu_name:
            vram_gb = round(self.gpu_vram_mb / 1024)
            parts.append(f"GPU: {self.gpu_name} {vram_gb}GB")
        else:
            parts.append("GPU: n/a")
        
        ki_status = "Ollama" if self.ollama_ok else "KI: Fallback"
        parts.append(ki_status)

        if self.ffmpeg_ok and self.ffmpeg_version:
            parts.append(f"FFmpeg {self.ffmpeg_version}")
        return "  |  ".join(parts)


def _check_ollama() -> bool:
    """Prueft ob Ollama laeuft, falls nicht: Auto-Start-Versuch."""
    import socket
    from pathlib import Path

    def is_port_open(port: int) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.5)
            return s.connect_ex(("localhost", port)) == 0

    if is_port_open(11434):
        return True

    # Versuch Ollama zu finden und zu starten
    paths = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Ollama" / "ollama.exe",
        Path("C:/Program Files/Ollama/ollama.exe"),
    ]
    
    for p in paths:
        if p.exists():
            try:
                logger.info("Starte Ollama automatisch: %s", p)
                subprocess.Popen(
                    [str(p), "serve"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    **_subprocess_kwargs()
                )
                return True # Als OK markieren, Dienst startet im Hintergrund
            except Exception as e:
                logger.warning("Fehler beim Auto-Start von Ollama: %s", e)
    
    return False


def _subprocess_kwargs() -> dict:
    kw: dict = {}
    if sys.platform == "win32":
        kw["creationflags"] = subprocess.CREATE_NO_WINDOW
    return kw


def _check_ffmpeg() -> tuple[bool, str, bool]:
    import re
    ffmpeg_ok = False
    ffmpeg_version = ""
    ffprobe_ok = False

    try:
        result = subprocess.run(
            [_FFMPEG_BIN, "-version"],
            capture_output=True, text=True, timeout=5,
            **_subprocess_kwargs(),
        )
        if result.returncode == 0:
            ffmpeg_ok = True
            m = re.search(r"ffmpeg version\s+(\S+)", result.stdout, re.IGNORECASE)
            if m:
                raw = m.group(1)
                vm = re.match(r"(\d+\.\d+(?:\.\d+)?)", raw)
                ffmpeg_version = vm.group(1) if vm else raw
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        logger.debug("ffmpeg check failed: %s", exc)

    try:
        r2 = subprocess.run(
            [_FFPROBE_BIN, "-version"],
            capture_output=True, text=True, timeout=5,
            **_subprocess_kwargs(),
        )
        ffprobe_ok = r2.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        logger.debug("ffprobe check failed: %s", exc)

    return ffmpeg_ok, ffmpeg_version, ffprobe_ok


def _check_cuda() -> tuple[bool, str, int]:
    cuda_ok = False
    gpu_name = ""
    vram_mb = 0
    try:
        import torch
        if torch.cuda.is_available():
            cuda_ok = True
            gpu_name = torch.cuda.get_device_name(0)
            props = torch.cuda.get_device_properties(0)
            vram_mb = props.total_memory // (1024 * 1024)
    except ImportError:
        logger.debug("torch not installed — GPU check skipped")
    except Exception as exc:
        logger.debug("CUDA check error: %s", exc)
    return cuda_ok, gpu_name, vram_mb


def _check_disk(path: Path) -> float:
    import shutil
    try:
        usage = shutil.disk_usage(path)
        return usage.free / (1024 ** 3)
    except Exception as exc:
        logger.debug("Disk check error: %s", exc)
        return 0.0


def check_system(app_root: Path | None = None) -> SystemStatus:
    if app_root is None:
        app_root = Path(__file__).parent.parent

    status = SystemStatus()
    futures: dict = {}
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="startup_check") as pool:
        futures["ffmpeg"] = pool.submit(_check_ffmpeg)
        futures["cuda"] = pool.submit(_check_cuda)
        futures["disk"] = pool.submit(_check_disk, app_root)
        futures["ollama"] = pool.submit(_check_ollama)

        for key, future in futures.items():
            try:
                if key == "ffmpeg":
                    ok, ver, probe_ok = future.result(timeout=8)
                    status.ffmpeg_ok = ok
                    status.ffmpeg_version = ver
                    status.ffprobe_ok = probe_ok
                elif key == "cuda":
                    ok, name, vram = future.result(timeout=3)
                    status.cuda_ok = ok
                    status.gpu_name = name
                    status.gpu_vram_mb = vram
                elif key == "disk":
                    status.disk_free_gb = future.result(timeout=4)
                    status.disk_ok = status.disk_free_gb >= 1.0
                elif key == "ollama":
                    status.ollama_ok = future.result(timeout=5)
            except Exception as exc:
                logger.warning("Startup check '%s' raised: %s", key, exc)

    if not status.ffmpeg_ok:
        status.errors.append(
            "FFmpeg nicht gefunden. Bitte FFmpeg installieren und PATH konfigurieren.\n"
            "Video-Import und Export funktionieren nicht.\n"
            "Installation: choco install ffmpeg"
        )
    elif not status.ffprobe_ok:
        status.warnings.append(
            "ffprobe nicht gefunden. Metadaten-Erkennung eingeschraenkt."
        )

    if not status.cuda_ok:
        gefunden = status.gpu_name if status.gpu_name else "Keine GPU erkannt"
        status.warnings.append(
            f"PB Studio benötigt eine NVIDIA GPU mit CUDA (GTX 1060 6GB+).\n"
            f"Gefunden: {gefunden}\n"
            "KI-Features (Demucs, SigLIP, beat_this) werden nicht funktionieren."
        )

    if not status.disk_ok:
        status.warnings.append(
            f"Wenig Speicherplatz: {status.disk_free_gb:.1f} GB frei (1 GB empfohlen)."
        )

    return status
