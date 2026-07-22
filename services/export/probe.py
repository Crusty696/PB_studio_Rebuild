"""AUFRAEUM B2 — ffprobe / Metadaten-Ermittlung des Export-Service.

Reiner Verbatim-Code-Move aus ``services/export_service.py`` (kein
Logik-Change). Enthaelt das Probe-Caching, die FPS/Codec/pix_fmt-Ermittlung
und die Preprocessing-Entscheidung. ``logger`` behaelt den Namen
``services.export_service`` (byte-gleiches Log-Routing).
"""

import json as _json
import logging
import subprocess
import threading

from services.timeout_constants import FFMPEG_PROBE_TIMEOUT_SEC
from services.ffmpeg_utils import parse_frame_rate, probe_duration, subprocess_kwargs

from services.export._common import FFPROBE, _CONCAT_TARGET_PIX_FMT

logger = logging.getLogger("services.export_service")


# K7: kanonische Implementierung nach services.ffmpeg_utils verschoben.
# Alias bleibt fuer in-Modul-Caller + Tests (test_b504_concat_utf8_outpoint).
_parse_frame_rate = parse_frame_rate


def _probe_video(file_path: str) -> dict:
    """Ermittelt Aufloesung, FPS, Codec, pix_fmt und Dauer eines Videos via ffprobe.

    Returns: {"width": int, "height": int, "fps": float, "avg_fps": float,
              "codec": str, "pix_fmt": str, "duration": float}
    Falls Probe fehlschlaegt: leeres dict.

    B-504: avg_frame_rate (VFR-Indiz), pix_fmt (Concat-Kompatibilitaet) und
    duration (outpoint-Trim in der Concat-Liste) ergaenzt.
    """
    try:
        cmd = [
            FFPROBE, "-v", "quiet",
            "-select_streams", "v:0",
            "-show_entries",
            "stream=width,height,r_frame_rate,avg_frame_rate,codec_name,"
            "pix_fmt,duration:format=duration",
            "-of", "json",
            file_path,
        ]
        kwargs = subprocess_kwargs()
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=FFMPEG_PROBE_TIMEOUT_SEC,
            encoding="utf-8", errors="replace", **kwargs,
        )
        if result.returncode != 0:
            return {}
        import json
        data = json.loads(result.stdout)
        streams = data.get("streams", [])
        if not streams:
            return {}
        s = streams[0]
        # FPS: r_frame_rate ist "30/1" oder "30000/1001" etc.
        fps = _parse_frame_rate(s.get("r_frame_rate", "0/1"))
        avg_fps = _parse_frame_rate(s.get("avg_frame_rate", "0/0"))
        # Dauer: Stream-Dauer bevorzugt, sonst Container-Dauer (z.B. MKV
        # hat oft keine Stream-Duration).
        duration = 0.0
        try:
            duration = float(s.get("duration") or 0.0)
        except (TypeError, ValueError):
            duration = 0.0
        if duration <= 0.0:
            try:
                duration = float(data.get("format", {}).get("duration") or 0.0)
            except (TypeError, ValueError):
                duration = 0.0
        return {
            "width": int(s.get("width", 0)),
            "height": int(s.get("height", 0)),
            "fps": round(fps, 2),
            "avg_fps": round(avg_fps, 2),
            "codec": s.get("codec_name", ""),
            "pix_fmt": s.get("pix_fmt", ""),
            "duration": duration,
        }
    except (subprocess.SubprocessError, OSError, _json.JSONDecodeError, ValueError) as e:
        logger.warning("[Export] ffprobe fehlgeschlagen fuer %s: %s", file_path, e)
        return {}


# Cache: Probe-Ergebnisse pro Dateipfad (gleiche Datei wird oft mehrfach referenziert)
_probe_cache: dict[str, dict] = {}
_probe_cache_lock = threading.Lock()


def clear_probe_cache():
    """H-3 FIX: Clears the probe cache to prevent unbounded memory growth and stale data."""
    with _probe_cache_lock:
        _probe_cache.clear()
    logger.debug("[Export] Probe cache cleared")


def _get_probed_info(file_path: str) -> dict:
    """Probe-Info aus Cache holen (bei Miss: einmal proben)."""
    with _probe_cache_lock:
        if file_path not in _probe_cache:
            _probe_cache[file_path] = _probe_video(file_path)
        return _probe_cache[file_path]


def _needs_preprocessing(file_path: str, target_w: int, target_h: int,
                          target_fps: float) -> bool:
    """Prueft ob ein Video vor dem Concat standardisiert werden muss.

    True wenn: andere Aufloesung, andere FPS, nicht-H.264 Codec,
    VFR-Indiz (avg_frame_rate weicht von r_frame_rate ab) oder
    abweichendes Pixelformat (B-504).
    """
    info = _get_probed_info(file_path)
    if not info:
        return True  # Im Zweifel: standardisieren
    # Aufloesung pruefen (Toleranz: exakt match oder kleiner mit Padding)
    if info["width"] != target_w or info["height"] != target_h:
        return True
    # FPS pruefen (Toleranz: 0.5 fps)
    if abs(info["fps"] - target_fps) > 0.5:
        return True
    # Codec: nur h264 kann direkt concat-kopiert werden
    if info["codec"] not in ("h264", "libx264"):
        return True
    # B-504: VFR-Indiz — avg_frame_rate weicht messbar von r_frame_rate ab.
    # Konservativ: nur werten wenn avg_fps bekannt (>0); "0/0"/unbekannt
    # zaehlt NICHT als Abweichung.
    avg_fps = info.get("avg_fps", 0.0)
    if avg_fps > 0.0 and abs(avg_fps - info["fps"]) > 0.5:
        return True
    # B-504: Pixelformat — konservativ nur bekannte Abweichungen werten:
    # pix_fmt muss vorhanden sein UND vom Concat-Ziel abweichen.
    pix_fmt = info.get("pix_fmt", "")
    if pix_fmt and pix_fmt != _CONCAT_TARGET_PIX_FMT:
        return True
    return False


def _probe_audio_duration(audio_path: str) -> float:
    """B-086: ffprobe-Helper fuer LUFS-Progress-Mapping. Returnt 0.0
    bei Fehlern (= kein Progress, aber kein Crash).
    """
    try:
        from services.startup_checks import get_ffprobe_bin
        ffprobe_bin = get_ffprobe_bin()
    except (ImportError, AttributeError, RuntimeError):
        return 0.0
    try:
        return probe_duration(
            audio_path, fallback=0.0, timeout=10, ffprobe_bin=ffprobe_bin,
        )
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        logger.debug("ffprobe duration failed for %s: %s", audio_path, exc)
    return 0.0
