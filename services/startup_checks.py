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

from services.timeout_constants import (
    STARTUP_DISK_CHECK_TIMEOUT_SEC,
    STARTUP_FFMPEG_CHECK_TIMEOUT_SEC,
    STARTUP_GPU_CHECK_TIMEOUT_SEC,
    STARTUP_MODEL_CHECK_TIMEOUT_SEC,
    STARTUP_OLLAMA_CHECK_TIMEOUT_SEC,
)

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_BIN_DIR = _PROJECT_ROOT / "bin"

def get_ffmpeg_bin():
    """Finds the FFmpeg binary, preferring the local bin/ folder."""
    # Suche zuerst im lokalen bin-Ordner (absoluter Pfad)
    local_ffmpeg = _BIN_DIR / ("ffmpeg.exe" if sys.platform == "win32" else "ffmpeg")
    if local_ffmpeg.exists():
        return str(local_ffmpeg.resolve())
    return os.environ.get("FFMPEG_PATH", "ffmpeg")

def get_ffprobe_bin():
    """Finds the FFprobe binary, preferring the local bin/ folder."""
    local_ffprobe = _BIN_DIR / ("ffprobe.exe" if sys.platform == "win32" else "ffprobe")
    if local_ffprobe.exists():
        return str(local_ffprobe.resolve())
    return os.environ.get("FFPROBE_PATH", "ffprobe")

_FFMPEG_BIN = get_ffmpeg_bin()
_FFPROBE_BIN = get_ffprobe_bin()
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
    beat_this_ok: bool = False
    demucs_ok: bool = False
    ml_warnings: list[str] = field(default_factory=list)
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
    """Prueft ob Ollama laeuft, falls nicht: Auto-Start-Versuch via OllamaService."""
    import time
    from services.ollama_service import OllamaService
    svc = OllamaService.get()
    if svc.is_ready:
        return True

    try:
        logger.info("Starte Ollama automatisch via OllamaService...")
        svc.start()
        # FIX H-17: Wait for Ollama to actually be ready before returning True
        # Poll is_ready with timeout to ensure server is actually running
        timeout = 30  # seconds
        start_time = time.time()
        while time.time() - start_time < timeout:
            if svc.is_ready:
                logger.info("Ollama ist bereit nach %.1fs", time.time() - start_time)
                return True
            time.sleep(0.5)
        logger.warning("Ollama start timeout nach %ds", timeout)
        return False
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
            capture_output=True, text=True, timeout=STARTUP_FFMPEG_CHECK_TIMEOUT_SEC,
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
            capture_output=True, text=True, timeout=STARTUP_FFMPEG_CHECK_TIMEOUT_SEC,
            **_subprocess_kwargs(),
        )
        ffprobe_ok = r2.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as exc:
        logger.debug("ffprobe check failed: %s", exc)

    return ffmpeg_ok, ffmpeg_version, ffprobe_ok


def _get_nvidia_driver_version() -> tuple[str, str]:
    """Ermittelt NVIDIA-Treiber-Version via WMI (Windows) oder nvidia-smi.

    Returns:
        (nvidia_version_str, gpu_name)  z.B. ("561.09", "NVIDIA GeForce GTX 1060")
        Leere Strings wenn nicht ermittelbar.
    """
    gpu_name = ""
    driver_ver = ""
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             "Get-CimInstance Win32_VideoController "
             "| Where-Object { $_.Name -match 'NVIDIA' } "
             "| Select-Object -First 1 Name, DriverVersion "
             "| Format-List"],
            capture_output=True, text=True, timeout=8,
            **_subprocess_kwargs(),
        )
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith("Name"):
                gpu_name = line.split(":", 1)[-1].strip()
            elif line.startswith("DriverVersion"):
                raw = line.split(":", 1)[-1].strip()
                # Windows-Format: 27.21.14.6140 → NVIDIA 461.40
                # Letzte zwei Gruppen konkatenieren und als 5-stellig lesen
                parts = raw.split(".")
                if len(parts) >= 4:
                    combined = parts[-2] + parts[-1]
                    # Letzte 5 Ziffern → z.B. "46140" → "461.40"
                    if len(combined) >= 5:
                        nv = combined[-5:-2] + "." + combined[-2:]
                        driver_ver = nv
                    else:
                        driver_ver = raw
                else:
                    driver_ver = raw
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError) as exc:
        logger.debug("NVIDIA driver version check via WMI failed: %s", exc)
    return driver_ver, gpu_name


# Mindest-Treiber-Versionen fuer PyTorch CUDA-Builds (Windows)
_MIN_DRIVER_FOR_CUDA = {
    "12.8": 570.0,
    "12.6": 560.0,
    "12.4": 550.0,
    "12.1": 530.0,
    "11.8": 522.0,
    "11.7": 516.0,
    "11.6": 510.0,
    "11.3": 461.0,
}


def _recover_gpu_error47() -> bool:
    """Surface Book 2 Fix: GPU aus Error-State (Code 47) reaktivieren.

    Das Surface Book 2 hat die GTX 1060 im abnehmbaren Dock.
    Windows setzt die GPU nach Treiber-Crashes in den "safe removal"
    Zustand (Error 47). Disable+Enable reaktiviert sie ohne Neustart.

    Returns:
        True wenn Recovery erfolgreich oder nicht noetig.
    """
    if sys.platform != "win32":
        return True
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             "Get-CimInstance Win32_VideoController "
             "| Where-Object { $_.Name -match 'NVIDIA' } "
             "| Select-Object -First 1 ConfigManagerErrorCode "
             "| Format-List"],
            capture_output=True, text=True, timeout=8,
            **_subprocess_kwargs(),
        )
        for line in result.stdout.splitlines():
            if "ConfigManagerErrorCode" in line:
                code = line.split(":", 1)[-1].strip()
                if code == "47":
                    logger.warning(
                        "GPU im Error-State (Code 47, Surface Book Dock). "
                        "Versuche automatische Reaktivierung..."
                    )
                    # Disable + Enable via PowerShell
                    recovery = subprocess.run(
                        ["powershell.exe", "-NoProfile", "-Command",
                         "$gpu = Get-PnpDevice | Where-Object "
                         "{ $_.FriendlyName -match 'NVIDIA' -and $_.Class -eq 'Display' }; "
                         "if ($gpu) { "
                         "Disable-PnpDevice -InstanceId $gpu.InstanceId -Confirm:$false; "
                         "Start-Sleep -Seconds 3; "
                         "Enable-PnpDevice -InstanceId $gpu.InstanceId -Confirm:$false; "
                         "Start-Sleep -Seconds 2; "
                         "$g2 = Get-CimInstance Win32_VideoController | Where-Object { $_.Name -match 'NVIDIA' }; "
                         "Write-Host $g2.ConfigManagerErrorCode "
                         "}"],
                        capture_output=True, text=True, timeout=20,
                        **_subprocess_kwargs(),
                    )
                    new_code = recovery.stdout.strip()
                    if new_code == "0":
                        logger.info("GPU erfolgreich reaktiviert (Error 47 -> OK)")
                        return True
                    else:
                        logger.error(
                            "GPU-Recovery fehlgeschlagen (Code %s). "
                            "PC-Neustart erforderlich.", new_code or "unbekannt"
                        )
                        return False
                elif code == "0":
                    return True  # GPU ist OK
    except (subprocess.TimeoutExpired, OSError, FileNotFoundError) as exc:
        logger.debug("GPU Error-47 Check fehlgeschlagen: %s", exc)
    return True


def _check_cuda() -> tuple[bool, str, int]:
    cuda_ok = False
    gpu_name = ""
    vram_mb = 0
    try:
        import torch

        # Surface Book 2: GPU aus Error-47 reaktivieren BEVOR CUDA initialisiert wird
        _recover_gpu_error47()

        # Treiber-Version zuerst ermitteln (unabhaengig von torch.cuda)
        driver_ver_str, wmi_gpu_name = _get_nvidia_driver_version()
        if wmi_gpu_name:
            gpu_name = wmi_gpu_name

        # PyTorch-CUDA-Version pruefen
        torch_cuda_ver = getattr(torch.version, "cuda", None) or ""
        logger.info("PyTorch CUDA compiled: %s, Treiber: %s", torch_cuda_ver, driver_ver_str)

        # Kompatibilitaets-Check: Treiber vs. PyTorch CUDA
        if driver_ver_str and torch_cuda_ver:
            try:
                driver_num = float(driver_ver_str)
                # Finde die passende Mindest-Version
                cuda_major_minor = ".".join(torch_cuda_ver.split(".")[:2])
                min_driver = _MIN_DRIVER_FOR_CUDA.get(cuda_major_minor, 0)
                if min_driver > 0 and driver_num < min_driver:
                    logger.error(
                        "TREIBER-INKOMPATIBEL: NVIDIA-Treiber %.2f ist zu alt fuer "
                        "PyTorch CUDA %s (mindestens %.0f benoetigt). "
                        "Bitte Treiber aktualisieren: https://www.nvidia.com/drivers/",
                        driver_num, torch_cuda_ver, min_driver,
                    )
                    return False, gpu_name, 0
            except (ValueError, TypeError):
                logger.debug("Konnte Treiber-Version nicht parsen: %s", driver_ver_str)

        # Erzwinge Initialisierung
        if hasattr(torch.cuda, "init"):
            torch.cuda.init()

        available = torch.cuda.is_available()
        logger.info("PyTorch CUDA available check: %s", available)

        if available:
            cuda_ok = True
            gpu_name = torch.cuda.get_device_name(0)
            props = torch.cuda.get_device_properties(0)
            vram_mb = props.total_memory // (1024 * 1024)
            logger.info("GPU erkannt: %s (%d MB VRAM)", gpu_name, vram_mb)
        else:
            if driver_ver_str:
                logger.warning(
                    "torch.cuda.is_available() ist False trotz Treiber %s. "
                    "Moeglicherweise falsche PyTorch-CUDA-Version installiert. "
                    "Installiert: torch %s (CUDA %s). "
                    "Reparatur: python scripts/fix_gpu_setup.py",
                    driver_ver_str, torch.__version__, torch_cuda_ver,
                )
            else:
                logger.warning(
                    "torch.cuda.is_available() ist False. "
                    "Kein NVIDIA-Treiber erkannt. "
                    "Bitte NVIDIA-Treiber installieren: https://www.nvidia.com/drivers/"
                )
    except ImportError:
        logger.error("torch nicht installiert — GPU check fehlgeschlagen")
    except Exception as exc:
        logger.error("Kritischer CUDA Check Fehler: %s", exc, exc_info=True)
    return cuda_ok, gpu_name, vram_mb


def _check_ml_packages() -> tuple[bool, bool]:
    """Prueft ob ML-Pakete installiert und Modelle lokal gecacht sind.

    Returns:
        (beat_this_ok, demucs_ok)
    """
    beat_this_ok = False
    demucs_ok = False

    # beat_this — pruefe nur Import (Modell wird beim ersten Einsatz geladen)
    try:
        import beat_this  # noqa: F401
        beat_this_ok = True
    except ImportError:
        logger.debug("beat_this nicht installiert")

    # demucs — pruefe Import
    try:
        import demucs  # noqa: F401
        demucs_ok = True
    except ImportError:
        logger.debug("demucs nicht installiert")

    return beat_this_ok, demucs_ok


def _check_disk(path: Path) -> float:
    import shutil
    try:
        usage = shutil.disk_usage(path)
        return usage.free / (1024 ** 3)
    except OSError as exc:
        logger.debug("Disk check error: %s", exc)
        return 0.0


def check_system(app_root: Path | None = None) -> SystemStatus:
    if app_root is None:
        app_root = Path(__file__).parent.parent

    status = SystemStatus()
    
    # CUDA-Check zuerst und im Haupt-Thread erzwingen, da Background-Threads oft Probleme mit GPU-Context haben
    logger.info("Starte CUDA-Check...")
    status.cuda_ok, status.gpu_name, status.gpu_vram_mb = _check_cuda()

    futures: dict = {}
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="startup_check") as pool:
        futures["ffmpeg"] = pool.submit(_check_ffmpeg)
        futures["disk"] = pool.submit(_check_disk, app_root)
        futures["ollama"] = pool.submit(_check_ollama)
        futures["ml"] = pool.submit(_check_ml_packages)

        for key, future in futures.items():
            try:
                if key == "ffmpeg":
                    ok, ver, probe_ok = future.result(timeout=STARTUP_FFMPEG_CHECK_TIMEOUT_SEC)
                    status.ffmpeg_ok = ok
                    status.ffmpeg_version = ver
                    status.ffprobe_ok = probe_ok
                elif key == "cuda":
                    ok, name, vram = future.result(timeout=STARTUP_GPU_CHECK_TIMEOUT_SEC)
                    status.cuda_ok = ok
                    status.gpu_name = name
                    status.gpu_vram_mb = vram
                elif key == "disk":
                    status.disk_free_gb = future.result(timeout=STARTUP_DISK_CHECK_TIMEOUT_SEC)
                    status.disk_ok = status.disk_free_gb >= 1.0
                elif key == "ollama":
                    status.ollama_ok = future.result(timeout=STARTUP_OLLAMA_CHECK_TIMEOUT_SEC)
                elif key == "ml":
                    bt_ok, dmc_ok = future.result(timeout=STARTUP_MODEL_CHECK_TIMEOUT_SEC)
                    status.beat_this_ok = bt_ok
                    status.demucs_ok = dmc_ok
            except (TimeoutError, RuntimeError, OSError) as exc:
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
        gefunden = status.gpu_name if status.gpu_name else "Keine kompatible NVIDIA GPU erkannt"
        # Detaillierte Fehlermeldung mit Reparaturanweisung
        try:
            import torch
            torch_ver = torch.__version__
            cuda_ver = getattr(torch.version, "cuda", "?")
        except ImportError:
            torch_ver = "nicht installiert"
            cuda_ver = "?"
        driver_ver, _ = _get_nvidia_driver_version()
        status.errors.append(
            f"GPU-BESCHLEUNIGUNG NICHT VERFUEGBAR\n"
            f"GPU: {gefunden}\n"
            f"NVIDIA-Treiber: {driver_ver or 'nicht erkannt'}\n"
            f"PyTorch: {torch_ver} (CUDA {cuda_ver})\n\n"
            "REPARATUR:\n"
            "1. NVIDIA-Treiber aktualisieren: https://www.nvidia.com/drivers/\n"
            "   (Mindestens Version 550+ fuer CUDA 12.4)\n"
            "2. PyTorch reparieren: python scripts/fix_gpu_setup.py\n"
            "3. PC neustarten\n\n"
            "HINWEIS: Modelle laufen ohne GPU extrem langsam auf der CPU."
        )

    # ML package availability warnings (non-blocking — Fallbacks sind aktiv)
    if not status.beat_this_ok:
        status.ml_warnings.append(
            "beat_this nicht installiert — Beat-Analyse nutzt librosa als Fallback "
            "(geringere Praezision). Installation: pip install beat_this"
        )
    if not status.demucs_ok:
        status.ml_warnings.append(
            "demucs nicht installiert — Stem-Separation nicht verfuegbar. "
            "Installation: pip install demucs"
        )

    if not status.disk_ok:
        status.warnings.append(
            f"Wenig Speicherplatz: {status.disk_free_gb:.1f} GB frei (1 GB empfohlen)."
        )

    return status
