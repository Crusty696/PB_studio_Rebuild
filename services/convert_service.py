"""Konvertierungs-Service mit NVENC Preset-Profilen.

Phase 1 Foundation — SEKTOR 5.
3 PoC-validierte Preset-Profile:
  - Edit-Proxy (540p): Schnelles Editing, kleine Dateien
  - Master (1080p): Finale Qualitaet mit NVENC
  - DaVinci-Proxy (720p): DNxHR LB fuer DaVinci Resolve Import

Verwendet FFmpeg -progress fuer sauberes Fortschritts-Parsing.
KEIN AV1 — Pascal-Karten (GTX 1060) haben keinen echten AV1-Encoder.
"""

from __future__ import annotations

import functools
import logging
import os
import re
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from database import APP_ROOT

logger = logging.getLogger(__name__)

PROXY_DIR = APP_ROOT / "storage" / "proxies"
MASTER_DIR = APP_ROOT / "exports"

# FFmpeg Pfad — Chocolatey oder PATH
FFMPEG = os.environ.get("FFMPEG_PATH", "ffmpeg")
FFPROBE = os.environ.get("FFPROBE_PATH", "ffprobe")

# Windows reserved device names (case-insensitive)
_WIN_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)


def _sanitize_ffmpeg_error(stderr: str, max_lines: int = 3) -> str:
    """Sanitize FFmpeg stderr for safe error messages — strip full paths."""
    if not stderr:
        return "(no stderr)"
    lines = stderr.strip().splitlines()
    tail = lines[-max_lines:] if len(lines) > max_lines else lines
    return "\n".join(tail)


def _safe_stem(stem: str) -> str:
    """Escape Windows reserved device names in file stems."""
    if stem.lower() in _WIN_RESERVED:
        return f"_{stem}"
    return stem


@dataclass
class ConvertPreset:
    """Ein Konvertierungs-Preset mit allen FFmpeg-Parametern."""
    name: str
    description: str
    video_codec: str
    audio_codec: str
    scale: str | None         # z.B. "960:540", None = original
    extra_vflags: list[str]   # Zusaetzliche Video-Filter
    codec_params: list[str]   # Codec-spezifische Parameter
    container: str            # Dateiendung (mp4, mxf)
    output_dir: Path


# Die 3 PoC-validierten Presets
PRESET_EDIT_PROXY = ConvertPreset(
    name="Edit-Proxy (540p)",
    description="Schneller Edit-Proxy: 540p, h264_nvenc, p1, cq28. ~50MB/h",
    video_codec="h264_nvenc",
    audio_codec="aac",
    scale="960:540",
    extra_vflags=[],
    codec_params=["-preset", "p1", "-rc", "vbr", "-cq", "28", "-b:v", "0"],
    container="mp4",
    output_dir=PROXY_DIR,
)

PRESET_MASTER_1080P = ConvertPreset(
    name="Master (1080p)",
    description="Finale Qualitaet: 1080p, h264_nvenc, p4, cq18, 15Mbps",
    video_codec="h264_nvenc",
    audio_codec="aac",
    scale=None,  # Original-Aufloesung beibehalten
    extra_vflags=[],
    codec_params=[
        "-preset", "p4", "-rc", "vbr", "-cq", "18",
        "-b:v", "15M", "-maxrate", "20M", "-bufsize", "30M",
    ],
    container="mp4",
    output_dir=MASTER_DIR,
)

PRESET_DAVINCI_PROXY = ConvertPreset(
    name="DaVinci-Proxy (720p)",
    description="DaVinci Resolve Import: 720p, DNxHR LB, YUV422p, PCM Audio",
    video_codec="dnxhd",
    audio_codec="pcm_s16le",
    scale="1280:720",
    extra_vflags=[],
    codec_params=["-profile:v", "dnxhr_lb", "-pix_fmt", "yuv422p"],  # BUG-009: pix_fmt ist kein Videofilter
    container="mxf",
    output_dir=PROXY_DIR,
)

# Alle verfuegbaren Presets
PRESETS = {
    "edit_proxy": PRESET_EDIT_PROXY,
    "master": PRESET_MASTER_1080P,
    "davinci": PRESET_DAVINCI_PROXY,
}


@functools.cache
def detect_nvenc() -> dict:
    """Prueft ob NVENC (h264_nvenc) verfuegbar ist.

    Returns:
        {
            "h264_nvenc": bool,
            "hevc_nvenc": bool,
            "cuda_hwaccel": bool,
            "ffmpeg_version": str,
        }
    """
    result = {"h264_nvenc": False, "hevc_nvenc": False,
              "cuda_hwaccel": False, "ffmpeg_version": "unknown"}
    try:
        # FFmpeg Version
        p = subprocess.run(
            [FFMPEG, "-version"], capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace",
        )
        if p.returncode == 0 and p.stdout:
            result["ffmpeg_version"] = p.stdout.strip().split("\n")[0]

        # Encoder pruefen
        p = subprocess.run(
            [FFMPEG, "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace",
        )
        if p.returncode == 0:
            result["h264_nvenc"] = "h264_nvenc" in p.stdout
            result["hevc_nvenc"] = "hevc_nvenc" in p.stdout

        # CUDA hwaccel
        p = subprocess.run(
            [FFMPEG, "-hide_banner", "-hwaccels"],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace",
        )
        if p.returncode == 0:
            result["cuda_hwaccel"] = "cuda" in p.stdout.lower()

    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning("NVENC-Detection fehlgeschlagen: %s", e)

    return result


def convert(
    input_path: str | Path,
    preset_name: str = "edit_proxy",
    output_path: str | Path | None = None,
    progress_cb: Callable[[int, str], None] | None = None,
) -> str:
    """Konvertiert eine Mediendatei mit dem gewaehlten Preset.

    Args:
        input_path: Pfad zur Quelldatei
        preset_name: "edit_proxy", "master" oder "davinci"
        output_path: Optionaler Ausgabepfad (sonst automatisch)
        progress_cb: Callback(percent_0_to_100, status_text)

    Returns:
        Pfad zur konvertierten Datei
    """
    preset = PRESETS.get(preset_name)
    if preset is None:
        raise ValueError(
            f"Unbekanntes Preset: {preset_name}. "
            f"Verfuegbar: {list(PRESETS.keys())}"
        )

    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Quelldatei nicht gefunden: {input_path}")

    # [H-02 FIX] NVENC-Fallback: Pruefe Verfuegbarkeit vor dem Encoding
    _nvenc_codecs = {"h264_nvenc", "hevc_nvenc"}
    if preset.video_codec in _nvenc_codecs:
        nvenc_info = detect_nvenc()
        if not nvenc_info.get("h264_nvenc"):
            logger.warning(
                "NVENC nicht verfuegbar (kein %s) — Fallback auf libx264 (CPU). "
                "Konvertierung wird langsamer sein.",
                preset.video_codec,
            )
            from dataclasses import replace as _dc_replace
            preset = _dc_replace(
                preset,
                video_codec="libx264",
                codec_params=["-preset", "medium", "-crf", "23"],
            )

    # Ausgabepfad bestimmen
    if output_path is None:
        preset.output_dir.mkdir(parents=True, exist_ok=True)
        suffix = f"_{preset_name}.{preset.container}"
        output_path = preset.output_dir / f"{_safe_stem(input_path.stem)}{suffix}"
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Bereits konvertiert? (nur wenn Datei > 0 Bytes)
    if output_path.exists() and output_path.stat().st_size > 0:
        logger.info("Ausgabe existiert bereits: %s", output_path)
        if progress_cb:
            progress_cb(100, "Bereits vorhanden")
        return str(output_path)
    elif output_path.exists():
        logger.warning("0-Byte Proxy gefunden, wird neu erstellt: %s", output_path)
        output_path.unlink(missing_ok=True)

    # Dauer fuer Progress-Berechnung ermitteln
    total_duration = _get_duration(str(input_path))

    # FFmpeg-Kommando zusammenbauen
    cmd = [FFMPEG, "-y", "-hide_banner", "-progress", "pipe:1"]

    # [H-02 FIX] Hardware-Decode nur wenn CUDA hwaccel tatsaechlich verfuegbar ist
    if preset.video_codec != "dnxhd" and preset.video_codec not in {"libx264", "libx265"}:
        nvenc_info = detect_nvenc()
        if nvenc_info.get("cuda_hwaccel"):
            cmd += ["-hwaccel", "cuda"]

    cmd += ["-i", str(input_path)]

    # Video-Filter
    vf_parts = []
    if preset.scale:
        vf_parts.append(f"scale={preset.scale}")
    vf_parts.extend(preset.extra_vflags)
    if vf_parts:
        # Nur -vf wenn es echte Filter gibt (nicht -pix_fmt etc.)
        filter_parts = [p for p in vf_parts if not p.startswith("-")]
        flag_parts = [p for p in vf_parts if p.startswith("-")]
        if filter_parts:
            cmd += ["-vf", ",".join(filter_parts)]
        cmd += flag_parts

    # Video-Codec
    cmd += ["-c:v", preset.video_codec]
    cmd += preset.codec_params

    # Audio-Codec
    if preset.audio_codec == "aac":
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    elif preset.audio_codec == "pcm_s16le":
        cmd += ["-c:a", "pcm_s16le"]
    else:
        cmd += ["-c:a", preset.audio_codec]

    cmd.append(str(output_path))

    logger.info("Konvertiere mit Preset '%s': %s", preset_name, input_path.name)

    # FFmpeg mit Progress-Parsing ausfuehren
    ffmpeg_stderr = _run_ffmpeg_with_progress(cmd, total_duration, progress_cb)

    if not output_path.exists():
        logger.error(f"[ConvertService] FFmpeg lief durch (rc=0), aber Ausgabedatei fehlt!")
        logger.error(f"[ConvertService] stderr: {ffmpeg_stderr[-1000:]}")
        raise RuntimeError(f"Konvertierung fehlgeschlagen: Ausgabe nicht erstellt. stderr: {_sanitize_ffmpeg_error(ffmpeg_stderr)}")

    file_size = output_path.stat().st_size
    size_mb = file_size / (1024 * 1024)
    if file_size == 0:
        logger.error(f"[ConvertService] FFmpeg lief durch (rc=0), aber Ausgabedatei ist 0 Bytes!")
        logger.error(f"[ConvertService] stderr: {ffmpeg_stderr[-1000:]}")
        output_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"Konvertierung fehlgeschlagen: Ausgabedatei ist 0 Bytes. stderr: {ffmpeg_stderr[-500:]}"
        )
    logger.info("Konvertierung abgeschlossen: %s (%.1f MB)", output_path.name, size_mb)

    return str(output_path)


def _get_duration(file_path: str) -> float:
    """Ermittelt die Dauer einer Mediendatei in Sekunden via ffprobe."""
    try:
        p = subprocess.run(
            [FFPROBE, "-v", "quiet", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", file_path],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
        if p.returncode == 0 and p.stdout.strip():
            return float(p.stdout.strip())
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError):
        pass
    return 0.0


def _run_ffmpeg_with_progress(
    cmd: list[str],
    total_duration: float,
    progress_cb: Callable[[int, str], None] | None,
) -> str:
    """Fuehrt FFmpeg aus und parst -progress pipe:1 fuer Fortschritt.

    PoC-validiert: -progress pipe:1 gibt key=value Paare auf stdout aus.
    Relevante Keys: out_time_ms, frame, speed, progress (= "end" am Schluss).
    """
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    process = subprocess.Popen(
        cmd,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        **kwargs,
    )

    stderr_lines = []
    def _drain_stderr():
        for line in process.stderr:
            stderr_lines.append(line)
    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    try:
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue

            if line.startswith("out_time_ms=") and total_duration > 0 and progress_cb:
                try:
                    time_us = int(line.split("=")[1])
                    current_sec = time_us / 1_000_000
                    pct = min(99, int(current_sec / total_duration * 100))
                    progress_cb(pct, f"{pct}%")
                except (ValueError, IndexError):
                    pass
            elif line.startswith("out_time=") and total_duration > 0 and progress_cb:
                try:
                    time_str = line.split("=")[1]
                    parts = time_str.split(":")
                    if len(parts) == 3:
                        h, m, s = float(parts[0]), float(parts[1]), float(parts[2])
                        current_sec = h * 3600 + m * 60 + s
                        pct = min(99, int(current_sec / total_duration * 100))
                        progress_cb(pct, f"{pct}%")
                except (ValueError, IndexError):
                    pass
            elif line == "progress=end":
                if progress_cb:
                    progress_cb(100, "Fertig")

        process.wait(timeout=600)
    except subprocess.TimeoutExpired:
        process.kill()
        raise RuntimeError("FFmpeg Timeout (600s)")
    finally:
        # Bug-32 Fix: Stelle sicher dass Process terminiert wird, auch wenn Exception auftritt
        if process.poll() is None:
            process.kill()
        stderr_thread.join(timeout=10)

    stderr = ''.join(stderr_lines)
    if process.returncode != 0:
        logger.error(f"[ConvertService] FFmpeg FEHLER (rc={process.returncode}):")
        logger.error(f"[ConvertService] stderr: {stderr[-1000:]}")
        raise RuntimeError(
            f"FFmpeg fehlgeschlagen (rc={process.returncode}):\n{stderr[-500:]}"
        )
    return stderr


def get_available_presets() -> list[dict]:
    """Gibt alle verfuegbaren Presets mit Details zurueck."""
    nvenc = detect_nvenc()
    result = []
    for key, preset in PRESETS.items():
        available = True
        if preset.video_codec == "h264_nvenc" and not nvenc["h264_nvenc"]:
            available = False
        result.append({
            "key": key,
            "name": preset.name,
            "description": preset.description,
            "available": available,
            "codec": preset.video_codec,
        })
    return result
