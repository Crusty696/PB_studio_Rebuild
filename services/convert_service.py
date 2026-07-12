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

import logging
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from services.timeout_constants import (
    FFMPEG_EXPORT_TIMEOUT_SEC,
    FFMPEG_PROBE_TIMEOUT_SEC,
    THREAD_JOIN_TIMEOUT_SEC,
)
from services.errors import ConversionError, FFmpegError, FFmpegTimeoutError
from services.ffmpeg_utils import (
    probe_duration,
    proxy_dir as _proxy_dir,
    sanitize_ffmpeg_error as _sanitize_ffmpeg_error,
    subprocess_kwargs,
)
from services.nvenc_policy import require_nvenc, required_message
from services.startup_checks import get_ffmpeg_bin, get_ffprobe_bin

logger = logging.getLogger(__name__)


def _master_dir() -> Path:
    """Returns master/export directory for the current project (lazy APP_ROOT read)."""
    import database.session as _session
    return _session.APP_ROOT / "exports"

# FFmpeg Pfad — Chocolatey oder PATH
FFMPEG = get_ffmpeg_bin()
FFPROBE = get_ffprobe_bin()

# Windows reserved device names (case-insensitive)
_WIN_RESERVED = frozenset(
    {"con", "prn", "aux", "nul"}
    | {f"com{i}" for i in range(1, 10)}
    | {f"lpt{i}" for i in range(1, 10)}
)


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
    output_dir: Path | None = None  # resolved lazily in convert(); None = derive from APP_ROOT


# Die 3 PoC-validierten Presets (output_dir resolved lazily in convert())
PRESET_EDIT_PROXY = ConvertPreset(
    name="Edit-Proxy (540p)",
    description="Schneller Edit-Proxy: 540p, h264_nvenc, p1, cq28. ~50MB/h",
    video_codec="h264_nvenc",
    audio_codec="aac",
    scale="960:540",
    extra_vflags=[],
    codec_params=["-preset", "p1", "-rc", "vbr", "-cq", "28", "-b:v", "0"],
    container="mp4",
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
)

# Alle verfuegbaren Presets
PRESETS = {
    "edit_proxy": PRESET_EDIT_PROXY,
    "master": PRESET_MASTER_1080P,
    "davinci": PRESET_DAVINCI_PROXY,
}


# M8-FIX: TTL-basiertes Caching statt permanentem @functools.cache.
# Cache wird nach 60 Sekunden invalidiert, sodass Aenderungen an
# FFmpeg/GPU-Treibern erkannt werden koennen.
_nvenc_cache: dict | None = None
_nvenc_cache_time: float = 0.0
_NVENC_CACHE_TTL: float = 60.0  # Sekunden
_nvenc_cache_lock = threading.Lock()


def detect_nvenc() -> dict:
    """Prueft ob NVENC (h264_nvenc) verfuegbar ist.

    M8-FIX: Ergebnis wird 60s gecacht und danach neu ermittelt.
    VAD-74-FIX: Echter 1-Frame Encode-Test statt nur Encoder-List-Check.

    Returns:
        {
            "h264_nvenc": bool,
            "hevc_nvenc": bool,
            "cuda_hwaccel": bool,
            "ffmpeg_version": str,
        }
    """
    global _nvenc_cache, _nvenc_cache_time

    now = time.monotonic()
    with _nvenc_cache_lock:
        if _nvenc_cache is not None and (now - _nvenc_cache_time) < _NVENC_CACHE_TTL:
            return _nvenc_cache

    result = {"h264_nvenc": False, "hevc_nvenc": False,
              "cuda_hwaccel": False, "ffmpeg_version": "unknown"}
    try:
        # FFmpeg Version
        p = subprocess.run(
            [FFMPEG, "-version"], capture_output=True, text=True, timeout=FFMPEG_PROBE_TIMEOUT_SEC,
            encoding="utf-8", errors="replace",
            **subprocess_kwargs(),
        )
        if p.returncode == 0 and p.stdout:
            result["ffmpeg_version"] = p.stdout.strip().split("\n")[0]

        # Encoder pruefen (nur Liste, kein echter Test)
        p = subprocess.run(
            [FFMPEG, "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=FFMPEG_PROBE_TIMEOUT_SEC,
            encoding="utf-8", errors="replace",
            **subprocess_kwargs(),
        )
        h264_in_list = False
        hevc_in_list = False
        if p.returncode == 0:
            h264_in_list = "h264_nvenc" in p.stdout
            hevc_in_list = "hevc_nvenc" in p.stdout

        # VAD-74: Echter 1-Frame Encode-Test fuer h264_nvenc
        if h264_in_list:
            p = subprocess.run(
                [FFMPEG, "-f", "lavfi", "-i", "nullsrc=s=256x256:d=0.04",
                 "-c:v", "h264_nvenc", "-f", "null", "-"],
                capture_output=True, timeout=FFMPEG_PROBE_TIMEOUT_SEC,
                encoding="utf-8", errors="replace",
                **subprocess_kwargs(),
            )
            if p.returncode == 0:
                result["h264_nvenc"] = True
            else:
                logger.warning(
                    "h264_nvenc in Encoder-Liste, aber 1-Frame Test fehlgeschlagen. "
                    "Vermutlich NVENC API-Inkompatibilitaet (Treiber zu alt). Fallback auf libx264."
                )
                result["h264_nvenc"] = False

        # VAD-74: Echter 1-Frame Encode-Test fuer hevc_nvenc
        if hevc_in_list:
            p = subprocess.run(
                [FFMPEG, "-f", "lavfi", "-i", "nullsrc=s=256x256:d=0.04",
                 "-c:v", "hevc_nvenc", "-f", "null", "-"],
                capture_output=True, timeout=FFMPEG_PROBE_TIMEOUT_SEC,
                encoding="utf-8", errors="replace",
                **subprocess_kwargs(),
            )
            if p.returncode == 0:
                result["hevc_nvenc"] = True
            else:
                logger.warning(
                    "hevc_nvenc in Encoder-Liste, aber 1-Frame Test fehlgeschlagen. "
                    "Vermutlich NVENC API-Inkompatibilitaet (Treiber zu alt)."
                )
                result["hevc_nvenc"] = False

        # CUDA hwaccel
        p = subprocess.run(
            [FFMPEG, "-hide_banner", "-hwaccels"],
            capture_output=True, text=True, timeout=FFMPEG_PROBE_TIMEOUT_SEC,
            encoding="utf-8", errors="replace",
            **subprocess_kwargs(),
        )
        if p.returncode == 0:
            result["cuda_hwaccel"] = "cuda" in p.stdout.lower()

    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning("NVENC-Detection fehlgeschlagen: %s", e)

    with _nvenc_cache_lock:
        _nvenc_cache = result
        _nvenc_cache_time = now
    return result


# F-011 Fix: NVENC Session Limit für Consumer GPUs (Pascal/GTX 1060)
# Begrenzt gleichzeitige Hardware-Encodes auf 2, um FFmpeg-Abstürze zu verhindern.
NVENC_SEMAPHORE = threading.Semaphore(2)


def convert(
    input_path: str | Path,
    preset_name: str = "edit_proxy",
    output_path: str | Path | None = None,
    progress_cb: Callable[[int, str], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    timeout: float | None = None,
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
        raise ConversionError(
            f"Unbekanntes Preset: {preset_name}. Verfuegbar: {list(PRESETS.keys())}",
            output_format=preset_name
        )

    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Quelldatei nicht gefunden: {input_path}")

    # [H-02 FIX] NVENC-Fallback: Pruefe Verfuegbarkeit vor dem Encoding
    _nvenc_codecs = {"h264_nvenc", "hevc_nvenc"}
    is_nvenc = preset.video_codec in _nvenc_codecs
    
    if is_nvenc:
        nvenc_info = detect_nvenc()
        # F-22 (B-354): prueffe den tatsaechlichen Preset-Codec (h264_nvenc ODER
        # hevc_nvenc), nicht nur h264 — sonst faellt ein HEVC-Preset selbst dann
        # auf libx264 zurueck, wenn hevc_nvenc funktioniert.
        if not nvenc_info.get(preset.video_codec):
            if require_nvenc():
                raise ConversionError(
                    required_message(
                        f"{preset.video_codec} nicht verfuegbar; CPU-Fallback verboten"
                    ),
                    input_file=str(input_path),
                    output_format=preset_name,
                )
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
            is_nvenc = False

    # Ausgabepfad bestimmen — lazy dir resolution, re-reads APP_ROOT each call
    if output_path is None:
        out_dir = _master_dir() if preset_name == "master" else _proxy_dir()
        out_dir.mkdir(parents=True, exist_ok=True)
        suffix = f"_{preset_name}.{preset.container}"
        output_path = out_dir / f"{_safe_stem(input_path.stem)}{suffix}"
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

    # B-584: h264_nvenc auf Pascal (GTX 1060) kann KEIN 10-bit. Eine
    # 10-bit-Quelle (yuv420p10le / p010le / HEVC Main10) wuerde sonst mit
    # "10 bit encode not supported" abbrechen. Bei 10-bit-Input ein
    # 8-bit-Downconvert (yuv420p) erzwingen. 8-bit-Input bleibt unveraendert.
    if is_nvenc:
        src_pix_fmt = _get_pix_fmt(str(input_path))
        if "10" in src_pix_fmt or src_pix_fmt.startswith("p010"):
            cmd += ["-pix_fmt", "yuv420p"]
            logger.info(
                "B-584: 10-bit-Quelle (%s) erkannt — erzwinge -pix_fmt yuv420p "
                "(h264_nvenc/Pascal ist 8-bit-only).", src_pix_fmt,
            )

    # Audio-Codec
    if preset.audio_codec == "aac":
        cmd += ["-c:a", "aac", "-b:a", "192k"]
    elif preset.audio_codec == "pcm_s16le":
        cmd += ["-c:a", "pcm_s16le"]
    else:
        cmd += ["-c:a", preset.audio_codec]

    cmd.append(str(output_path))

    logger.info("Konvertiere mit Preset '%s': %s", preset_name, input_path.name)

    # F-011 Fix: Semaphore nutzen für NVENC-Tasks
    if is_nvenc:
        logger.debug("[ConvertService] Warte auf NVENC-Slot...")
        with NVENC_SEMAPHORE:
            from services.brain.gpu_serializer import get_default_serializer
            logger.info("[ConvertService] GpuSerializer.acquire('render') wartet")
            with get_default_serializer().acquire("render"):
                logger.info("[ConvertService] GpuSerializer holder='render' aktiv")
                try:
                    ffmpeg_stderr = _run_ffmpeg_with_progress(
                        cmd, total_duration, progress_cb, cancel_check=cancel_check,
                        timeout=timeout,
                    )
                finally:
                    logger.info("[ConvertService] GpuSerializer holder='render' wird freigegeben")
    else:
        ffmpeg_stderr = _run_ffmpeg_with_progress(
            cmd, total_duration, progress_cb, cancel_check=cancel_check,
            timeout=timeout,
        )

    if not output_path.exists():
        logger.error(f"[ConvertService] FFmpeg lief durch (rc=0), aber Ausgabedatei fehlt!")
        logger.error(f"[ConvertService] stderr: {ffmpeg_stderr[-1000:]}")
        raise ConversionError(
            f"Konvertierung fehlgeschlagen: Ausgabe nicht erstellt. stderr: {_sanitize_ffmpeg_error(ffmpeg_stderr)}",
            input_file=str(input_path),
            output_format=preset_name
        )

    file_size = output_path.stat().st_size
    size_mb = file_size / (1024 * 1024)
    if file_size == 0:
        logger.error(f"[ConvertService] FFmpeg lief durch (rc=0), aber Ausgabedatei ist 0 Bytes!")
        logger.error(f"[ConvertService] stderr: {ffmpeg_stderr[-1000:]}")
        output_path.unlink(missing_ok=True)
        raise ConversionError(
            f"Konvertierung fehlgeschlagen: Ausgabedatei ist 0 Bytes. stderr: {ffmpeg_stderr[-500:]}",
            input_file=str(input_path),
            output_format=preset_name
        )
    logger.info("Konvertierung abgeschlossen: %s (%.1f MB)", output_path.name, size_mb)

    return str(output_path)


def _get_duration(file_path: str) -> float:
    """Ermittelt die Dauer einer Mediendatei in Sekunden via ffprobe."""
    try:
        return probe_duration(
            file_path, fallback=0.0,
            timeout=FFMPEG_PROBE_TIMEOUT_SEC, ffprobe_bin=FFPROBE,
        )
    except (subprocess.TimeoutExpired, ValueError, FileNotFoundError) as e:
        logger.warning("Getting media duration for '%s': %s", file_path, e)
    return 0.0


def _get_pix_fmt(file_path: str) -> str:
    """B-584: Ermittelt das Pixelformat des ersten Video-Streams via ffprobe.

    Liefert z.B. "yuv420p", "yuv420p10le", "p010le". Leerer String bei
    Fehler/unbekannt — der Caller behandelt das als "kein erzwungener
    Downconvert".
    """
    try:
        p = subprocess.run(
            [FFPROBE, "-v", "quiet", "-select_streams", "v:0",
             "-show_entries", "stream=pix_fmt",
             "-of", "default=noprint_wrappers=1:nokey=1", file_path],
            capture_output=True, text=True, timeout=FFMPEG_PROBE_TIMEOUT_SEC,
            encoding="utf-8", errors="replace",
        )
        if p.returncode == 0 and p.stdout.strip():
            return p.stdout.strip().splitlines()[0].strip()
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        logger.warning("Getting pix_fmt for '%s': %s", file_path, e)
    return ""


def _run_ffmpeg_with_progress(
    cmd: list[str],
    total_duration: float,
    progress_cb: Callable[[int, str], None] | None,
    cancel_check: Callable[[], bool] | None = None,
    timeout: float | None = None,
) -> str:
    """Fuehrt FFmpeg aus und parst -progress pipe:1 fuer Fortschritt.

    PoC-validiert: -progress pipe:1 gibt key=value Paare auf stdout aus.
    Relevante Keys: out_time_ms, frame, speed, progress (= "end" am Schluss).

    B-116 Fix: ``cancel_check`` kann eine ``Callable[[], bool]`` sein.
    Wird in der Progress-Schleife UND vom Watchdog-Thread regelmaessig
    abgefragt; bei True wird der ffmpeg-Prozess terminiert und eine
    ``FFmpegError("Convert abgebrochen")`` geworfen.

    B-059 Fix: ``timeout`` (Wall-Clock-Sekunden). Ein zusaetzlicher
    Watchdog-Thread killt den ffmpeg-Prozess wenn die Wall-Clock-Zeit
    ueberschritten wird — auch wenn FFmpeg keine Progress-Output mehr
    schreibt (Hang im I/O-Retry, korrupter Codec, NVENC-Treiber-Bug).
    Default = ``FFMPEG_EXPORT_TIMEOUT_SEC`` (600s).
    """
    import time as _time

    if timeout is None:
        timeout = float(FFMPEG_EXPORT_TIMEOUT_SEC)

    kwargs = subprocess_kwargs()

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
    cancelled = threading.Event()
    timed_out = threading.Event()
    def _drain_stderr():
        for line in process.stderr:
            stderr_lines.append(line)
    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    cancel_watchdog = None
    if cancel_check is not None:
        def _cancel_watch():
            while process.poll() is None:
                try:
                    if cancel_check():
                        cancelled.set()
                        process.terminate()
                        try:
                            process.wait(timeout=2.0)
                        except subprocess.TimeoutExpired:
                            process.kill()
                        return
                except Exception:
                    return
                _time.sleep(0.2)
        cancel_watchdog = threading.Thread(target=_cancel_watch, daemon=True)
        cancel_watchdog.start()

    # B-059 Fix: Wall-Clock-Watchdog — killt den Prozess wenn FFmpeg
    # ueber `timeout` Sekunden laeuft (z.B. Hang ohne stdout-Output).
    timeout_watchdog = None
    _start_ts = _time.monotonic()
    if timeout is not None and timeout > 0:
        def _timeout_watch():
            while process.poll() is None:
                if _time.monotonic() - _start_ts >= timeout:
                    timed_out.set()
                    try:
                        process.terminate()
                        try:
                            process.wait(timeout=2.0)
                        except subprocess.TimeoutExpired:
                            process.kill()
                    except Exception:
                        pass
                    return
                _time.sleep(0.5)
        timeout_watchdog = threading.Thread(target=_timeout_watch, daemon=True)
        timeout_watchdog.start()

    try:
        for line in process.stdout:
            if cancel_check is not None and cancel_check():
                cancelled.set()
                process.terminate()
                break
            line = line.strip()
            if not line:
                continue

            if line.startswith("out_time_ms=") and total_duration > 0 and progress_cb:
                # FFmpeg liefert "out_time_ms=N/A" beim ersten Tick bevor Pipe-Stream
                # initialisiert ist — silent ignorieren, kein Warning.
                raw = line.split("=", 1)[1] if "=" in line else ""
                if raw and raw != "N/A":
                    try:
                        time_us = int(raw)
                        current_sec = time_us / 1_000_000
                        pct = min(99, int(current_sec / total_duration * 100))
                        progress_cb(pct, f"{pct}%")
                    except (ValueError, IndexError) as e:
                        logger.warning("Parsing FFmpeg out_time_ms progress: %s", e)
            elif line.startswith("out_time=") and total_duration > 0 and progress_cb:
                try:
                    time_str = line.split("=")[1]
                    parts = time_str.split(":")
                    if len(parts) == 3:
                        h, m, s = float(parts[0]), float(parts[1]), float(parts[2])
                        current_sec = h * 3600 + m * 60 + s
                        pct = min(99, int(current_sec / total_duration * 100))
                        progress_cb(pct, f"{pct}%")
                except (ValueError, IndexError) as e:
                    logger.warning("Parsing FFmpeg out_time progress: %s", e)
            elif line == "progress=end":
                if progress_cb:
                    progress_cb(100, "Fertig")

        process.wait(timeout=timeout if timeout is not None else FFMPEG_EXPORT_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        process.kill()
        timed_out.set()
    finally:
        # Bug-32 Fix: Stelle sicher dass Process terminiert wird, auch wenn Exception auftritt
        if process.poll() is None:
            process.kill()
        stderr_thread.join(timeout=THREAD_JOIN_TIMEOUT_SEC)
        if cancel_watchdog is not None:
            cancel_watchdog.join(timeout=THREAD_JOIN_TIMEOUT_SEC)
        if timeout_watchdog is not None:
            timeout_watchdog.join(timeout=THREAD_JOIN_TIMEOUT_SEC)

    # B-210: User-Intent (Cancel) hat Vorrang vor System-Intent (Timeout).
    # Wenn beide Watchdogs gleichzeitig feuern, soll der User die korrekte
    # "Abgebrochen"-Meldung sehen statt eines verwirrenden "Timeout".
    if cancelled.is_set():
        raise FFmpegError(
            "Convert abgebrochen (User-Cancel)",
            returncode=-1,
            stderr=''.join(stderr_lines),
        )

    if timed_out.is_set():
        raise FFmpegTimeoutError(int(timeout if timeout is not None else FFMPEG_EXPORT_TIMEOUT_SEC))

    stderr = ''.join(stderr_lines)
    if process.returncode != 0:
        logger.error(f"[ConvertService] FFmpeg FEHLER (rc={process.returncode}):")
        logger.error(f"[ConvertService] stderr: {stderr[-1000:]}")
        raise FFmpegError(
            f"FFmpeg fehlgeschlagen:\n{stderr[-500:]}",
            returncode=process.returncode,
            stderr=stderr
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
