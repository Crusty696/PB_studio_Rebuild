"""Export-Service: Fuegt Timeline-Clips via FFmpeg zu einem finalen Video zusammen.

Phase 3 Erweiterung: Crossfades, Farbkorrektur, Stem-Mix, Auto-Ducking.
Optimiert fuer viele kleine Segmente (Auto-Edit to Beat).
"""

import json as _json
import logging
import os
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path, PurePosixPath, PureWindowsPath

from sqlalchemy.orm import Session
from database import engine, TimelineEntry, AudioTrack, VideoClip
from services.timeout_constants import (
    FFMPEG_LUFS_MEASURE_TIMEOUT_SEC,
    FFMPEG_LUFS_NORMALIZE_TIMEOUT_SEC,
    FFMPEG_PROBE_TIMEOUT_SEC,
    FFMPEG_RENDER_TIMEOUT_SEC,
    THREAD_JOIN_TIMEOUT_SEC,
)
from services.startup_checks import get_ffmpeg_bin, get_ffprobe_bin

# FIX-1.2: FFmpeg-Pfad konfigurierbar (identisch mit convert_service.py)
FFMPEG = get_ffmpeg_bin()
FFPROBE = get_ffprobe_bin()

_export_nvenc_available: bool | None = None


def _video_encode_args() -> list[str]:
    """Video-Codec-Args fuer Export-Re-Encodes (F-7 / B-339).

    Bevorzugt ``h264_nvenc`` gemaess GPU-Hartregel (GTX 1060), faellt auf
    ``libx264`` (CPU) zurueck wenn NVENC nicht verfuegbar ist — so bleibt der
    Export ueberall lauffaehig. NVENC-Parameter spiegeln das erprobte
    ``master``-Preset aus ``convert_service``.
    """
    global _export_nvenc_available
    if _export_nvenc_available is None:
        try:
            from services.convert_service import detect_nvenc
            _export_nvenc_available = bool(detect_nvenc().get("h264_nvenc"))
        except Exception:
            _export_nvenc_available = False
    if _export_nvenc_available:
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr",
                "-cq", "18", "-b:v", "15M"]
    return ["-c:v", "libx264", "-preset", "fast", "-crf", "23"]


def _sanitize_ffmpeg_error(stderr: str, max_lines: int = 3) -> str:
    """Sanitize FFmpeg stderr for safe error messages."""
    if not stderr:
        return "(no stderr)"
    lines = stderr.strip().splitlines()
    tail = lines[-max_lines:] if len(lines) > max_lines else lines
    return "\n".join(tail)

logger = logging.getLogger(__name__)


def _probe_video(file_path: str) -> dict:
    """Ermittelt Aufloesung, FPS und Codec eines Videos via ffprobe.

    Returns: {"width": int, "height": int, "fps": float, "codec": str}
    Falls Probe fehlschlaegt: leeres dict.
    """
    try:
        cmd = [
            FFPROBE, "-v", "quiet",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate,codec_name",
            "-of", "json",
            file_path,
        ]
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
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
        fps = 0.0
        rfr = s.get("r_frame_rate", "0/1")
        if "/" in rfr:
            num, den = rfr.split("/")
            fps = float(num) / float(den) if float(den) > 0 else 0.0
        else:
            fps = float(rfr)
        return {
            "width": int(s.get("width", 0)),
            "height": int(s.get("height", 0)),
            "fps": round(fps, 2),
            "codec": s.get("codec_name", ""),
        }
    except (subprocess.SubprocessError, OSError, _json.JSONDecodeError, ValueError) as e:
        logger.warning("[Export] ffprobe fehlgeschlagen fuer %s: %s", file_path, e)
        return {}


# Cache: Probe-Ergebnisse pro Dateipfad (gleiche Datei wird oft mehrfach referenziert)
_probe_cache: dict[str, dict] = {}
_probe_cache_lock = threading.Lock()


def _sanitize_concat_path(path: str) -> str:
    """B-168: Concat-Demuxer-Pfad sanitisieren.

    Single-Quote-Escape (`'` → `'\\''`), Backslash → Slash. Steuerzeichen
    (Newline, CR, NUL) sind nicht maskierbar — sie wuerden den concat-
    Demuxer-Parser auseinander reissen oder die concat-Datei truncieren.
    Daher: Pfad mit Control-Char ablehnen statt silent corruption.
    """
    if any(c in path for c in ("\n", "\r", "\x00")):
        raise ValueError(
            f"Pfad enthaelt nicht-maskierbare Steuerzeichen "
            f"(newline/CR/NUL): {path!r}"
        )
    return path.replace("\\", "/").replace("'", "'\\''")


def clear_probe_cache():
    """H-3 FIX: Clears the probe cache to prevent unbounded memory growth and stale data."""
    with _probe_cache_lock:
        _probe_cache.clear()
    logger.debug("[Export] Probe cache cleared")


def _needs_preprocessing(file_path: str, target_w: int, target_h: int,
                          target_fps: float) -> bool:
    """Prueft ob ein Video vor dem Concat standardisiert werden muss.

    True wenn: andere Aufloesung, andere FPS, oder nicht-H.264 Codec.
    """
    with _probe_cache_lock:
        if file_path not in _probe_cache:
            _probe_cache[file_path] = _probe_video(file_path)
        info = _probe_cache[file_path]
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
    return False


def _preprocess_segment(seg: dict, index: int, w: str, h: str, fps: float,
                         temp_files: list, cancel_check=None) -> dict:
    """Standardisiert ein einzelnes Segment auf target-Aufloesung/FPS/H.264.

    Gibt ein processed_segment dict zurueck mit dem Pfad zur standardisierten Datei.

    B-126: ``cancel_check`` wird durchgereicht zu ``_run_ffmpeg`` damit
    der Pre-Encode mid-segment cancellable ist.
    """
    source_start = seg.get("source_start", 0.0)
    source_duration = seg.get("source_duration", seg["end"] - seg["start"])

    tmp = tempfile.NamedTemporaryFile(
        suffix=".mp4", delete=False, prefix=f"pb_std_{index}_"
    )
    tmp.close()
    temp_files.append(tmp.name)

    vf = (
        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}"
    )

    std_cmd = [
        FFMPEG, "-y",
        "-ss", f"{source_start:.3f}",
        "-i", seg["path"],
        "-t", f"{source_duration:.3f}",
        "-vf", vf,
        *_video_encode_args(),
        "-an", tmp.name,
    ]
    _run_ffmpeg(std_cmd, timeout=FFMPEG_RENDER_TIMEOUT_SEC,
                cancel_check=cancel_check)
    return {
        "path": tmp.name,
        "duration": source_duration,
        "inpoint": None,
        "outpoint": None,
        "standardized": True,
    }

def _get_export_dir() -> Path:
    """Return export directory for the current project (lazy APP_ROOT read).

    BUG-FIX: Was module-level constant that became stale after set_project().
    Now reads APP_ROOT at call time so project switches are respected.
    """
    import database.session as _session
    return _session.APP_ROOT / "exports"


def _resolve_export_output_path(export_dir: Path, output_name: str) -> Path:
    """Build an export path from a filename-only output name."""
    raw_name = str(output_name).strip()
    if not raw_name:
        raw_name = "output.mp4"

    win_path = PureWindowsPath(raw_name)
    posix_path = PurePosixPath(raw_name)
    parts = set(win_path.parts) | set(posix_path.parts)
    if (
        win_path.is_absolute()
        or posix_path.is_absolute()
        or bool(win_path.drive)
        or ".." in parts
        or "\\" in raw_name
        or "/" in raw_name
        or win_path.name != raw_name
        or posix_path.name != raw_name
    ):
        raise ValueError("Ungueltiger output_name: nur ein Dateiname im Export-Ordner ist erlaubt")

    output_path = (export_dir / raw_name).resolve()
    export_root = export_dir.resolve()
    if output_path.parent != export_root:
        raise ValueError("Ungueltiger output_name: Export-Pfad verlaesst den Export-Ordner")
    return output_path


def _source_duration_from_entry(
    entry, fallback_duration: float, clip_duration: float | None = None
) -> float:
    source_start = entry.source_start or 0.0
    source_end = entry.source_end
    if source_end is not None and source_start is not None:
        source_duration = source_end - source_start
    else:
        source_duration = fallback_duration
    if source_duration <= 0:
        raise ValueError(
            f"Ungueltige source_duration fuer TimelineEntry {getattr(entry, 'id', '?')}: "
            f"{source_duration:.3f}s"
        )
    if source_start < 0:
        raise ValueError(
            f"Ungueltiger source_start fuer TimelineEntry {getattr(entry, 'id', '?')}: "
            f"{source_start:.3f}s"
        )
    if clip_duration is not None and clip_duration > 0:
        source_end_abs = source_start + source_duration
        if source_end_abs > clip_duration + 1e-6:
            raise ValueError(
                f"Source-Bereich fuer TimelineEntry {getattr(entry, 'id', '?')} "
                f"ueberschreitet clip duration {clip_duration:.3f}s"
            )
    return source_duration


def _cleanup_orphan_tempfiles(max_age_hours: float = 1.0) -> int:
    """B-118: entfernt zurueckgelassene ``pb_std_*`` und ``pb_lufs_*``
    Tempfiles aelter als ``max_age_hours`` aus dem System-Tempdir.

    Wird von ``export_timeline`` und ``export_preview`` am Anfang
    aufgerufen. Defensive: scheitert nie an PermissionError oder
    OSError — Cleanup ist best-effort.

    Returns: Anzahl tatsaechlich geloeschter Files.
    """
    import time as _time
    deleted = 0
    cutoff = _time.time() - (max_age_hours * 3600.0)
    try:
        tmpdir = Path(tempfile.gettempdir())
        for pattern in ("pb_std_*", "pb_lufs_*"):
            for tf in tmpdir.glob(pattern):
                try:
                    if tf.is_file() and tf.stat().st_mtime < cutoff:
                        tf.unlink()
                        deleted += 1
                except (OSError, PermissionError):
                    # File still locked oder verschwand zwischen glob+stat
                    pass
    except Exception as exc:
        logger.debug("orphan-tempfile cleanup skipped: %s", exc)
    if deleted:
        logger.info("B-118: %d orphan pb_std_/pb_lufs_ tempfile(s) entfernt.", deleted)
    return deleted


def _prepare_normalized_audio(audio_path: str | None, temp_files: list,
                               progress_cb=None, step: int = 0,
                               total_steps: int = 5,
                               cancel_check=None) -> tuple[str | None, int]:
    """LUFS-Normalisierung auf Audio anwenden. Gibt (normalized_path, step) zurueck.

    B-125: ``cancel_check`` wird durchgereicht zu _normalize_audio_lufs.
    B-086: zusaetzlich ``progress_cb`` durchreichen damit der UI-Balken
    waehrend der 2-4 Min LUFS-Phase nicht eingefroren bleibt. Audio-
    Dauer wird via ffprobe ermittelt, sonst kann Pass1/Pass2-Progress
    nicht in Prozent ausgedrueckt werden.
    """
    if not audio_path:
        return None, step
    if progress_cb:
        step += 1
        progress_cb(int(step / total_steps * 100), "Audio-Normalisierung (LUFS)...")
    norm_tmp = tempfile.NamedTemporaryFile(
        suffix=".wav", delete=False, prefix="pb_lufs_"
    )
    norm_tmp.close()
    temp_files.append(norm_tmp.name)

    # B-086: Audio-Dauer ermitteln fuer Progress-Mapping. ffprobe ist
    # schnell (<100ms) — Fehler degraded auf 0 → kein Progress, aber
    # kein Crash. Der step-base/range im step-progress wird wieder
    # korrekt berechnet.
    audio_duration = _probe_audio_duration(audio_path)

    step_pct_base = int(step / total_steps * 100)
    step_pct_range = int(100 / total_steps)

    def _lufs_progress(inner_pct: int, _msg: str) -> None:
        if progress_cb is None:
            return
        global_pct = step_pct_base + int(inner_pct / 100.0 * step_pct_range)
        progress_cb(min(99, global_pct), "Audio-Normalisierung (LUFS)...")

    if _normalize_audio_lufs(
        audio_path,
        norm_tmp.name,
        cancel_check=cancel_check,
        progress_cb=_lufs_progress if progress_cb is not None else None,
        total_duration=audio_duration,
    ):
        return norm_tmp.name, step
    return audio_path, step


def _probe_audio_duration(audio_path: str) -> float:
    """B-086: ffprobe-Helper fuer LUFS-Progress-Mapping. Returnt 0.0
    bei Fehlern (= kein Progress, aber kein Crash).
    """
    try:
        from services.startup_checks import get_ffprobe_bin
        ffprobe_bin = get_ffprobe_bin()
    except (ImportError, AttributeError, RuntimeError):
        return 0.0
    cmd = [
        ffprobe_bin, "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        audio_path,
    ]
    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace", **kwargs,
        )
        if result.returncode == 0:
            return float(result.stdout.strip())
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        logger.debug("ffprobe duration failed for %s: %s", audio_path, exc)
    return 0.0


def export_timeline(project_id: int = 1, output_name: str = "output.mp4",
                    resolution: str = "1920x1080", fps: float = 30.0,
                    progress_cb=None, cancel_check=None) -> str:
    """Exportiert alle Timeline-Eintraege als zusammengeschnittenes Video.

    B-116: ``cancel_check`` ist optional eine Callable[[], bool], die
    waehrend des laufenden ffmpeg-Calls regelmaessig abgefragt wird.
    Bei True wird der Subprocess terminiert."""
    # B-118: orphan tempfile cleanup beim Start — fruehere Exports
    # konnten unter Windows-File-Locks ihre Tempfiles nicht aufraeumen.
    _cleanup_orphan_tempfiles()
    # BUG-003: Cache leeren — re-enkodierte Proxies haetten sonst veraltete Metadaten
    # M-7 FIX: Use thread-safe clear function instead of direct dict access
    clear_probe_cache()
    # F-sprint3: Validiere Resolution frueh — vor DB-Zugriff und Dateisystem-Operationen
    try:
        w, h = resolution.split("x")
        # M-28 FIX: Validate that width and height are numeric
        int(w)
        int(h)
    except ValueError:
        raise ValueError(
            f"Ungültige Auflösung Format: '{resolution}'. Erwartet: WIDTHxHEIGHT (z.B. '1920x1080')"
        )

    export_dir = _get_export_dir()
    export_dir.mkdir(parents=True, exist_ok=True)
    output_path = _resolve_export_output_path(export_dir, output_name)

    with Session(engine) as session:
        entries = (
            session.query(TimelineEntry)
            .filter_by(project_id=project_id)
            .order_by(TimelineEntry.start_time)
            .all()
        )
        if not entries:
            raise ValueError("Keine Timeline-Eintraege zum Exportieren vorhanden")

        video_entries = [e for e in entries if e.track == "video"]
        audio_entries = [e for e in entries if e.track == "audio"]

        # Bug-12 Fix: Bulk-Load aller benötigten VideoClips verhindert N+1
        # (vorher: 1 SELECT pro Segment → bei 100 Auto-Edit Segmenten = 100 Queries)
        _vid_ids = [ve.media_id for ve in video_entries]
        _clips_by_id = (
            {c.id: c for c in session.query(VideoClip).filter(
                VideoClip.id.in_(_vid_ids), VideoClip.deleted_at.is_(None)
            ).all()}
            if _vid_ids else {}
        )

        video_segments = []
        for ve in video_entries:
            clip = _clips_by_id.get(ve.media_id)
            if clip:
                source_start = ve.source_start or 0.0
                source_end = ve.source_end
                seg_duration = ve.end_time - ve.start_time if ve.end_time else (clip.duration or 10.0)
                # Source-Duration aus Source-Offsets, Fallback auf Timeline-Duration
                source_duration = _source_duration_from_entry(
                    ve, seg_duration, clip.duration
                )
                video_segments.append({
                    "path": clip.file_path,
                    "start": ve.start_time,
                    "end": ve.end_time or (ve.start_time + seg_duration),
                    "duration": clip.duration or 10.0,
                    "source_start": source_start,
                    "source_duration": source_duration,
                    "crossfade": ve.crossfade_duration or 0.0,
                    "brightness": ve.brightness or 0.0,
                    "contrast": ve.contrast or 1.0,
                })

        audio_path = None
        if audio_entries:
            track = session.query(AudioTrack).filter(
                AudioTrack.id == audio_entries[0].media_id, AudioTrack.deleted_at.is_(None)
            ).first()
            if track:
                audio_path = track.file_path

    if not video_segments:
        raise ValueError("Keine Video-Clips auf der Timeline")

    # Berechne total_steps basierend auf Audio-Normalisierung
    total_steps = 5 if audio_path else 4

    # Strategie: Bei vielen Segmenten (>10) oder ohne Effekte -> Concat
    # Bei wenigen mit Effekten -> Filtergraph
    has_effects = any(
        seg["crossfade"] > 0 or seg["brightness"] != 0.0 or seg["contrast"] != 1.0
        for seg in video_segments
    )

    if has_effects:
        return _export_with_filtergraph(
            video_segments, audio_path, output_path,
            w, h, fps, progress_cb, total_steps,
            cancel_check=cancel_check,
        )
    else:
        return _export_optimized_concat(
            video_segments, audio_path, output_path,
            w, h, fps, progress_cb, total_steps,
            cancel_check=cancel_check,
        )


def _export_optimized_concat(video_segments, audio_path, output_path,
                              w, h, fps, progress_cb, total_steps,
                              cancel_check=None):
    """Concat-Export mit automatischer Vorverarbeitung nicht-konformer Clips.

    PERF-FIX: Clips die nicht target-konform sind (andere Aufloesung/FPS/Codec)
    werden VOR dem Concat einzeln standardisiert. Dadurch kann der Concat-Schritt
    ohne den schweren scale/pad/fps-Filter laufen → massiv schneller.
    Clips die bereits konform sind werden direkt concat-kopiert.
    """
    step = 0
    temp_files = []
    target_w, target_h = int(w), int(h)

    if progress_cb:
        step += 1
        progress_cb(int(step / total_steps * 100), "Pruefe Video-Formate...")

    try:
        # Phase 1: Ermittle welche Clips Vorverarbeitung brauchen
        unique_paths = set(seg["path"] for seg in video_segments)
        needs_std = {}
        for path in unique_paths:
            needs_std[path] = _needs_preprocessing(path, target_w, target_h, fps)

        std_count = sum(1 for v in needs_std.values() if v)
        logger.info(
            "[Export] %d/%d einzigartige Quellen brauchen Standardisierung "
            "(target: %sx%s @ %.0ffps H.264)",
            std_count, len(unique_paths), w, h, fps,
        )

        # B-085: Disk-Space-Pre-Check vor dem Preprocessing.
        # Bei vielen kleinen Cuts auf 1080p CRF23 fast: ~0.25 MB/s Material →
        # bei 900 Segmenten × 4s = 3600 s × 0.25 MB/s ≈ 900 MB pre-encoded
        # Temp. Mit 50% Sicherheits-Marge muessen wir mindestens das
        # Doppelte freihaben, sonst scheitert der Render mid-way mit
        # ``No space left on device`` und 30+ Min Arbeit ist verloren.
        #
        # Heuristik: target_w * target_h * 0.2 bytes/frame ist ein konser-
        # vativer CRF23-fast-Richtwert (echte Werte 0.10-0.35, abhängig
        # vom Material). Wir nehmen 0.2 als Mittel + 50% Marge.
        _segments_to_preprocess = [
            seg for seg in video_segments
            if needs_std.get(seg["path"], True)
            or seg.get("brightness", 0.0) != 0.0
            or seg.get("contrast", 1.0) != 1.0
        ]
        if _segments_to_preprocess:
            import shutil as _shutil
            import tempfile as _tf
            _bytes_per_sec = float(target_w) * float(target_h) * 0.2 * float(fps)
            _total_sec = sum(
                float(seg.get("source_duration", seg["end"] - seg["start"]))
                for seg in _segments_to_preprocess
            )
            _est_bytes = int(_total_sec * _bytes_per_sec)
            _free_bytes = _shutil.disk_usage(_tf.gettempdir()).free
            _required = int(_est_bytes * 1.5)  # 50% Marge
            logger.info(
                "[Export] Disk-Pre-Check: ~%.1f GB Temp benoetigt (×1.5 Marge: "
                "%.1f GB), %.1f GB frei in %s",
                _est_bytes / 1e9, _required / 1e9, _free_bytes / 1e9,
                _tf.gettempdir(),
            )
            if _free_bytes < _required:
                raise RuntimeError(
                    f"Nicht genug Speicher in {_tf.gettempdir()} fuer Export-"
                    f"Preprocessing: ~{_est_bytes/1e9:.1f} GB benoetigt "
                    f"(×1.5 Marge: {_required/1e9:.1f} GB), nur "
                    f"{_free_bytes/1e9:.1f} GB frei. "
                    f"Bitte mehr Platz schaffen oder kuerzeres Projekt rendern."
                )

        # Phase 2: Segmente vorverarbeiten oder direkt uebernehmen
        processed_segments = []
        # Cache: bereits standardisierte Dateien pro (pfad, source_start, source_duration)
        _std_cache: dict[tuple, str] = {}

        for i, seg in enumerate(video_segments):
            has_color = seg["brightness"] != 0.0 or seg["contrast"] != 1.0
            source_start = seg.get("source_start", 0.0)
            source_duration = seg.get("source_duration", seg["end"] - seg["start"])
            need_preprocess = needs_std.get(seg["path"], True) or has_color

            if need_preprocess:
                # Vorverarbeitung noetig: Standardisierung + ggf. Farbkorrektur
                cache_key = (seg["path"], round(source_start, 3),
                             round(source_duration, 3),
                             round(seg.get("brightness", 0.0), 2),
                             round(seg.get("contrast", 1.0), 2))

                if cache_key in _std_cache:
                    # Gleicher Clip+Ausschnitt bereits standardisiert → wiederverwenden
                    processed_segments.append({
                        "path": _std_cache[cache_key],
                        "duration": source_duration,
                        "inpoint": None,
                        "outpoint": None,
                    })
                else:
                    tmp = tempfile.NamedTemporaryFile(
                        suffix=".mp4", delete=False, prefix=f"pb_std_{i}_"
                    )
                    tmp.close()
                    temp_files.append(tmp.name)

                    # Farbkorrektur + Standardisierung in einem Durchgang
                    vf_parts = []
                    if has_color:
                        _b = max(-1.0, min(1.0, float(seg.get('brightness') or 0.0)))
                        _c = max(0.0, min(3.0, float(seg.get('contrast') or 1.0)))
                        vf_parts.append(f"eq=brightness={_b}:contrast={_c}")
                    vf_parts.append(
                        f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}"
                    )
                    vf = ",".join(vf_parts)

                    std_cmd = [
                        FFMPEG, "-y",
                        "-ss", f"{source_start:.3f}",
                        "-i", seg["path"],
                        "-t", f"{source_duration:.3f}",
                        "-vf", vf,
                        *_video_encode_args(),
                        "-an", tmp.name,
                    ]
                    # B-126: per-segment cancel propagation.
                    _run_ffmpeg(std_cmd, timeout=FFMPEG_RENDER_TIMEOUT_SEC,
                                cancel_check=cancel_check)
                    _std_cache[cache_key] = tmp.name
                    processed_segments.append({
                        "path": tmp.name,
                        "duration": source_duration,
                        "inpoint": None,
                        "outpoint": None,
                    })

                if progress_cb and (i + 1) % 50 == 0:
                    pct = int(step / total_steps * 100) + int(
                        (i + 1) / len(video_segments) * 15
                    )
                    progress_cb(min(pct, 95), f"Standardisiere {i+1}/{len(video_segments)}...")

            elif source_start > 0.01:
                # Bereits konform + Source-Offset: concat inpoint/outpoint
                processed_segments.append({
                    "path": seg["path"],
                    "duration": source_duration,
                    "inpoint": source_start,
                    "outpoint": source_start + source_duration,
                })
            else:
                # Bereits konform, kein Offset: direkt
                processed_segments.append({
                    "path": seg["path"],
                    "duration": source_duration,
                    "inpoint": None,
                    "outpoint": None,
                })

        # Concat-Datei erstellen
        concat_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, prefix="pb_concat_"
        )
        temp_files.append(concat_file.name)

        for ps in processed_segments:
            # FIX H-11 + B-168: Proper FFmpeg concat demuxer escaping.
            # Single-Quote-Escape, Backslash → Slash, Reject Control-Chars.
            safe_path = _sanitize_concat_path(ps["path"])
            concat_file.write(f"file '{safe_path}'\n")
            if ps["inpoint"] is not None:
                concat_file.write(f"inpoint {ps['inpoint']:.3f}\n")
            if ps["outpoint"] is not None:
                concat_file.write(f"outpoint {ps['outpoint']:.3f}\n")
            else:
                concat_file.write(f"duration {ps['duration']:.3f}\n")
        concat_file.close()

        if progress_cb:
            step += 1
            progress_cb(int(step / total_steps * 100), f"FFmpeg Concat ({len(video_segments)} Clips)...")

        # PERF: Wenn ALLE Segmente standardisiert wurden, kein Output-Filter noetig
        all_standardized = all(
            needs_std.get(seg["path"], True) or (seg["brightness"] != 0.0 or seg["contrast"] != 1.0)
            for seg in video_segments
        )

        cmd = [
            FFMPEG, "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_file.name,
        ]

        # LUFS-Normalisierung auf Audio anwenden (wenn vorhanden)
        normalized_audio, step = _prepare_normalized_audio(
            audio_path, temp_files, progress_cb, step, total_steps,
            cancel_check=cancel_check,
        )

        if normalized_audio:
            cmd += ["-i", normalized_audio]

        if all_standardized:
            # Alle Clips bereits standardisiert → kein Filter noetig, Stream-Copy
            cmd += ["-c:v", "copy"]
            logger.info("[Export] Alle Clips standardisiert → Stream-Copy (schnell)")
        else:
            # Fallback: globaler Filter fuer gemischte Quellen
            filter_str = (
                f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}"
            )
            cmd += ["-vf", filter_str, *_video_encode_args()]

        if normalized_audio:
            cmd += ["-c:a", "aac", "-b:a", "192k",
                    "-map", "0:v:0", "-map", "1:a:0", "-shortest"]
        else:
            cmd += ["-an"]

        cmd.append(str(output_path))

        # FIX-1.2: Dynamischer Timeout basierend auf Segment-Anzahl.
        # Heuristik: ~30s pro Segment (Decode+Scale+Encode) + 600s Basis.
        # Bei 896 Segmenten: 600 + 896*30 = 27480s (~7.6h) — genuegend Puffer.
        # Frueher: fix 7200s → Timeout bei vielen Segmenten.
        num_segs = len(video_segments)
        estimated_duration = sum(s.get("source_duration", s["end"] - s["start"]) for s in video_segments)
        dynamic_timeout = max(7200, 600 + num_segs * 30)
        logger.info(
            "[Export] Concat-Export: %d Segmente, ~%.0fs geschaetzte Dauer, Timeout=%ds",
            num_segs, estimated_duration, dynamic_timeout,
        )
        _run_ffmpeg(cmd, timeout=dynamic_timeout, progress_cb=progress_cb,
                    total_duration=estimated_duration,
                    cancel_check=cancel_check)

        if progress_cb:
            step += 1
            progress_cb(100, "Export abgeschlossen")

    finally:
        for tf in temp_files:
            try:
                Path(tf).unlink(missing_ok=True)
            except PermissionError:
                logger.warning(
                    "B-007: Temp-Datei '%s' konnte nicht gelöscht werden (Windows-Dateilock). "
                    "Wird beim nächsten Export bereinigt.",
                    tf,
                )

    if not Path(output_path).exists() or Path(output_path).stat().st_size == 0:
        raise RuntimeError(f"FFmpeg-Export fehlgeschlagen: Ausgabedatei fehlt oder leer: {output_path}")
    return str(Path(output_path).resolve())


def _export_with_filtergraph(video_segments, audio_path, output_path,
                             w, h, fps, progress_cb, total_steps,
                             cancel_check=None):
    """Komplexer Export mit Filtergraph (Crossfades + Farbkorrektur)."""
    step = 0
    temp_files = []

    if progress_cb:
        step += 1
        progress_cb(int(step / total_steps * 100), "Baue FFmpeg-Kommando...")

    cmd = [FFMPEG, "-y"]
    for seg in video_segments:
        source_start = seg.get("source_start", 0.0)
        source_duration = seg.get("source_duration", seg["end"] - seg["start"])
        if source_start > 0.01:
            cmd += ["-ss", f"{source_start:.3f}"]
        cmd += ["-t", f"{source_duration:.3f}", "-i", seg["path"]]
    # LUFS-Normalisierung auf Audio anwenden (wenn vorhanden)
    normalized_audio, step = _prepare_normalized_audio(
        audio_path, temp_files, progress_cb, step, total_steps,
        cancel_check=cancel_check,
    )

    if normalized_audio:
        cmd += ["-i", normalized_audio]

    n = len(video_segments)
    audio_input_idx = n if normalized_audio else None

    if progress_cb:
        step += 1
        progress_cb(int(step / total_steps * 100), "Filtergraph wird erstellt...")

    filter_parts = []
    for i, seg in enumerate(video_segments):
        base_filter = (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}"
        )
        _b2 = max(-1.0, min(1.0, float(seg.get('brightness') or 0.0)))
        _c2 = max(0.0, min(3.0, float(seg.get('contrast') or 1.0)))
        if _b2 != 0.0 or _c2 != 1.0:
            base_filter += f",eq=brightness={_b2}:contrast={_c2}"
        filter_parts.append(f"[{i}:v]{base_filter}[v{i}]")

    # Segment-Dauern: Source-Duration wenn vorhanden, sonst Timeline-Duration
    seg_durations = [
        seg.get("source_duration", seg["end"] - seg["start"])
        for seg in video_segments
    ]

    current_label = None
    if n == 0:
        raise ValueError("Keine Video-Segmente in _export_with_filtergraph()")
    elif n == 1:
        current_label = "v0"
    else:
        # F-014 Fix: Kumulativer Offset-Akkumulator fuer korrekte xfade-Berechnung
        accumulated_duration = seg_durations[0]

        xfade_dur = min(video_segments[1].get("crossfade", 0.0), 2.0)
        if xfade_dur > 0:
            offset = max(0.1, accumulated_duration - xfade_dur)
            filter_parts.append(
                f"[v0][v1]xfade=transition=fade:duration={xfade_dur}:offset={offset}[xf0]"
            )
            accumulated_duration = accumulated_duration + seg_durations[1] - xfade_dur
        else:
            filter_parts.append("[v0][v1]concat=n=2:v=1:a=0[xf0]")
            accumulated_duration += seg_durations[1]
        current_label = "xf0"

        for i in range(2, n):
            xfade_dur = min(video_segments[i].get("crossfade", 0.0), 2.0)
            if xfade_dur > 0:
                offset = max(0.1, accumulated_duration - xfade_dur)
                filter_parts.append(
                    f"[{current_label}][v{i}]xfade=transition=fade:"
                    f"duration={xfade_dur}:offset={offset}[xf{i-1}]"
                )
                accumulated_duration = accumulated_duration + seg_durations[i] - xfade_dur
            else:
                filter_parts.append(
                    f"[{current_label}][v{i}]concat=n=2:v=1:a=0[xf{i-1}]"
                )
                accumulated_duration += seg_durations[i]
            current_label = f"xf{i-1}"

    filter_complex = ";".join(filter_parts)
    # B-169: Lange Filtergraphs ueber filter_complex_script ausweichen.
    # Windows CreateProcess lpCommandLine limit ist 32767 chars; bei 100+
    # Segmenten sprengt der Inline-Filter dieses Limit (~150 B base + 80 B
    # xfade pro seg = 23 KB bei n=100). FFmpeg liest filter_complex_script
    # aus einer Datei und ist damit unbeschraenkt.
    if len(filter_complex) > 16000 or len(video_segments) > 50:
        fcs = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, prefix="pb_fcs_",
            encoding="utf-8",
        )
        fcs.write(filter_complex)
        fcs.close()
        temp_files.append(fcs.name)
        cmd += ["-filter_complex_script", fcs.name]
        logger.info(
            "[Export] filter_complex_script genutzt (%d segments, %d chars)",
            len(video_segments), len(filter_complex),
        )
    else:
        cmd += ["-filter_complex", filter_complex]
    cmd += ["-map", f"[{current_label}]"]

    if normalized_audio and audio_input_idx is not None:
        cmd += ["-map", f"{audio_input_idx}:a:0",
                "-c:a", "aac", "-b:a", "192k", "-shortest"]
    else:
        cmd += ["-an"]

    cmd += _video_encode_args()
    cmd.append(str(output_path))

    if progress_cb:
        step += 1
        progress_cb(int(step / total_steps * 100), "FFmpeg-Export mit Effekten...")

    try:
        # FIX-1.2: Dynamischer Timeout auch fuer Filtergraph-Export
        n = len(video_segments)
        estimated_duration = sum(
            seg.get("source_duration", seg["end"] - seg["start"])
            for seg in video_segments
        )
        dynamic_timeout = max(1800, 600 + n * 60)  # Filtergraph braucht mehr pro Segment
        _run_ffmpeg(cmd, timeout=dynamic_timeout, progress_cb=progress_cb,
                    total_duration=estimated_duration,
                    cancel_check=cancel_check)
    finally:
        for tf in temp_files:
            try:
                Path(tf).unlink(missing_ok=True)
            except PermissionError:
                logger.warning(
                    "B-007: Temp-Datei '%s' konnte nicht gelöscht werden (Windows-Dateilock). "
                    "Wird beim nächsten Export bereinigt.",
                    tf,
                )

    if progress_cb:
        step += 1
        progress_cb(100, "Export mit Effekten abgeschlossen")

    if not Path(output_path).exists() or Path(output_path).stat().st_size == 0:
        raise RuntimeError(f"FFmpeg-Export fehlgeschlagen: Ausgabedatei fehlt oder leer: {output_path}")
    return str(Path(output_path).resolve())


def _run_subprocess_cancellable(
    cmd: list[str], timeout: int, cancel_check=None,
    progress_cb=None, total_duration: float = 0.0,
    progress_base_pct: int = 0, progress_range_pct: int = 100,
):
    """B-125: ``subprocess.run``-aequivalent mit Cancel-Watchdog.

    Faehrt cmd via Popen, polled cancel_check alle 200ms, terminiert
    den Process bei True. Wenn cancel_check None ist, faellt es auf
    blockierendes ``subprocess.run`` zurueck.

    B-086: optional ``progress_cb(pct, msg)`` parsed
    ``out_time_ms=...``-Lines aus stdout (FFmpeg ``-progress pipe:1``)
    und ruft den Callback waehrend des Laufs. ``total_duration`` ist
    die Audio-/Video-Dauer in Sekunden — sonst kann der Prozentwert
    nicht berechnet werden. ``progress_base_pct`` + ``progress_range_pct``
    erlauben einem Caller mit mehrphasigem Lauf (Pass1+Pass2) die
    inneren Prozente auf einen Bereich zu mappen (z.B. 50-100 fuer
    Pass2).

    Returns: subprocess.CompletedProcess (returncode/stdout/stderr).
    Raises: RuntimeError("LUFS-Normalisierung abgebrochen") bei Cancel.
    """
    kwargs: dict = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW

    if cancel_check is None and progress_cb is None:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace", **kwargs,
        )

    process = subprocess.Popen(
        cmd, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", **kwargs,
    )
    cancelled = threading.Event()

    def _cancel_watch():
        while process.poll() is None:
            try:
                if cancel_check is not None and cancel_check():
                    cancelled.set()
                    process.terminate()
                    try:
                        process.wait(timeout=2.0)
                    except subprocess.TimeoutExpired:
                        process.kill()
                    return
            except Exception as exc:  # broad: watchdog must keep running
                # B-167: nicht stumm zurueckkehren — sonst stirbt der Watchdog
                # bei einem temporaeren cancel_check-Fehler und der ffmpeg-Lauf
                # ist nicht mehr abbrechbar.
                logger.warning(
                    "[Cancel-Watch] cancel_check raised: %s — Watchdog endet.", exc,
                )
                return
            time.sleep(0.2)

    watchdog = threading.Thread(target=_cancel_watch, daemon=True)
    watchdog.start()

    # B-086: Progress-Stream-Reader liest stdout zeilenweise und parsed
    # ``out_time_ms`` aus dem ffmpeg ``-progress pipe:1`` Output. Laeuft
    # in einem eigenen Thread damit ``communicate`` nicht blockiert.
    stdout_lines: list[str] = []
    progress_active = (
        progress_cb is not None and total_duration > 0.0 and process.stdout is not None
    )

    def _progress_reader():
        try:
            for line in process.stdout:  # type: ignore[union-attr]
                stdout_lines.append(line)
                if not progress_active:
                    continue
                line = line.strip()
                if line.startswith("out_time_ms=") and progress_cb is not None:
                    try:
                        time_us = int(line.split("=", 1)[1])
                    except (ValueError, IndexError):
                        continue
                    current_sec = time_us / 1_000_000
                    if total_duration > 0:
                        inner_pct = max(0.0, min(1.0, current_sec / total_duration))
                        global_pct = int(
                            progress_base_pct + inner_pct * progress_range_pct
                        )
                        try:
                            progress_cb(min(99, global_pct), "")
                        except Exception as cb_exc:  # broad: ein Callback-Fehler darf den Run nicht killen
                            logger.debug("progress_cb raised: %s", cb_exc)
        except Exception as reader_exc:  # broad: Reader darf nicht crashen
            logger.debug("progress reader exited: %s", reader_exc)

    reader = None
    if progress_active or progress_cb is not None:
        reader = threading.Thread(target=_progress_reader, daemon=True)
        reader.start()

    try:
        if reader is not None:
            # stdout wird im Reader-Thread gelesen — wir warten nur auf stderr.
            try:
                _, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                _, stderr = process.communicate()
            reader.join(timeout=THREAD_JOIN_TIMEOUT_SEC)
            stdout = "".join(stdout_lines)
        else:
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
    finally:
        watchdog.join(timeout=THREAD_JOIN_TIMEOUT_SEC)

    if cancelled.is_set():
        raise RuntimeError("LUFS-Normalisierung abgebrochen (User-Cancel)")

    return subprocess.CompletedProcess(
        args=cmd, returncode=process.returncode,
        stdout=stdout, stderr=stderr,
    )


def _normalize_audio_lufs(input_path: str, output_path: str,
                          target_lufs: float = -14.0,
                          cancel_check=None,
                          progress_cb=None,
                          total_duration: float = 0.0) -> bool:
    """LUFS Zwei-Pass Audio-Normalisierung via FFmpeg loudnorm.

    Pass 1: Misst die integrierte Lautstaerke (I), Loudness Range (LRA),
            True Peak (TP) und Threshold.
    Pass 2: Wendet die gemessenen Werte an um auf target_lufs zu normalisieren.

    B-125: ``cancel_check`` Callable wird zwischen Pass1 und Pass2 sowie
    waehrend des Subprocess-Runs alle 200ms abgefragt. Bei Cancel raised
    es RuntimeError, sodass der Caller (export_timeline) sauber abbrechen
    kann.

    B-086: optional ``progress_cb(pct, msg)`` + ``total_duration`` (Sek).
    Pass1 mappt 0-50%, Pass2 mappt 50-100% des inneren LUFS-Schritts.
    Vorher war LUFS ein UI-Freeze von 2-4 Min bei langem Audio — jetzt
    laeuft die Progress-Bar kontinuierlich durch.

    Returns True bei Erfolg, False bei Fehler (Original wird dann verwendet).
    """
    try:
        # B-125: Cancel-Check zwischen den Passes.
        if cancel_check is not None and cancel_check():
            return False

        # B-086: ``-progress pipe:1`` aktiviert ``out_time_ms=...``-Output
        # in stdout, der vom Subprocess-Helper geparsed wird.
        measure_cmd = [
            FFMPEG, "-i", input_path,
            "-af", "loudnorm=print_format=json",
            "-progress", "pipe:1",
            "-f", "null", "-"
        ]
        result = _run_subprocess_cancellable(
            measure_cmd,
            timeout=FFMPEG_LUFS_MEASURE_TIMEOUT_SEC,
            cancel_check=cancel_check,
            progress_cb=progress_cb,
            total_duration=total_duration,
            progress_base_pct=0,
            progress_range_pct=50,
        )
        if result.returncode != 0:
            logger.warning("[LUFS] Pass 1 fehlgeschlagen (rc=%d): %s",
                           result.returncode, _sanitize_ffmpeg_error(result.stderr))
            return False
        # loudnorm JSON steht in stderr
        stderr = result.stderr
        json_start = stderr.rfind("{")
        json_end = stderr.rfind("}") + 1
        if json_start < 0 or json_end <= json_start:
            logger.warning("[LUFS] Konnte loudnorm-Messung nicht parsen")
            return False

        measured = _json.loads(stderr[json_start:json_end])
        input_i = measured.get("input_i", "-24.0")
        input_lra = measured.get("input_lra", "7.0")
        input_tp = measured.get("input_tp", "-2.0")
        input_thresh = measured.get("input_thresh", "-34.0")

        # B-125: Cancel-Check zwischen Pass1 und Pass2.
        if cancel_check is not None and cancel_check():
            return False

        loudnorm_filter = (
            f"loudnorm=I={target_lufs}:LRA=11:TP=-1"
            f":measured_I={input_i}:measured_LRA={input_lra}"
            f":measured_TP={input_tp}:measured_thresh={input_thresh}"
            f":linear=true"
        )
        norm_cmd = [
            FFMPEG, "-y", "-i", input_path,
            "-af", loudnorm_filter,
            "-ar", "48000",
            "-c:a", "pcm_s24le",
            "-progress", "pipe:1",
            output_path,
        ]
        pass2_result = _run_subprocess_cancellable(
            norm_cmd,
            timeout=FFMPEG_LUFS_NORMALIZE_TIMEOUT_SEC,
            cancel_check=cancel_check,
            progress_cb=progress_cb,
            total_duration=total_duration,
            progress_base_pct=50,
            progress_range_pct=50,
        )
        if pass2_result.returncode != 0:
            logger.warning("[LUFS] Pass 2 fehlgeschlagen (rc=%d): %s",
                           pass2_result.returncode, _sanitize_ffmpeg_error(pass2_result.stderr))
            return False
        if Path(output_path).exists() and Path(output_path).stat().st_size > 0:
            logger.info("[LUFS] Normalisierung erfolgreich: %s -> %.1f LUFS",
                        input_path, target_lufs)
            return True
        return False
    except (subprocess.SubprocessError, OSError, ValueError) as e:
        logger.warning("[LUFS] Normalisierung fehlgeschlagen: %s", e)
        return False


def _run_ffmpeg(cmd: list[str], timeout: int = 600, progress_cb=None,
                total_duration: float = 0.0,
                cancel_check=None):
    """Dispatcher: serialisiert NVENC-Encodes app-weit (Befund 1 / Review 2026-05-23).

    Root-Cause-Fix statt Pflaster: Ein NVENC-Export-Encode darf auf der GTX 1060
    (Pascal, ~2-3 NVENC-Sessions) nicht gleichzeitig mit Proxy-/Convert-NVENC
    laufen, sonst ``OpenEncodeSessionEx failed``. Wir halten denselben
    ``gpu_serializer`` (der zusaetzlich den legacy ``GPU_EXECUTION_LOCK`` greift),
    den ``convert_service`` schon nutzt — damit ist app-weit nur EIN GPU-Consumer
    aktiv. libx264 (CPU) braucht keinen Lock.
    """
    if any("nvenc" in str(a) for a in cmd):
        from services.brain_v3.gpu_serializer import get_default_serializer
        with get_default_serializer().acquire("export_render"):
            return _run_ffmpeg_impl(cmd, timeout, progress_cb, total_duration, cancel_check)
    return _run_ffmpeg_impl(cmd, timeout, progress_cb, total_duration, cancel_check)


def _run_ffmpeg_impl(cmd: list[str], timeout: int = 600, progress_cb=None,
                     total_duration: float = 0.0,
                     cancel_check=None):
    """Fuehrt FFmpeg aus — mit Popen + Progress-Parsing statt blockierendem subprocess.run.

    FIX-1.2: Wechsel von subprocess.run() (blockiert ohne Progress) zu subprocess.Popen
    mit -progress pipe:1 Parsing (identisch mit convert_service.py). Ermoeglicht:
    - Echtzeit-Progress-Updates waehrend des Exports
    - Sauberen Abbruch bei Timeout (process.kill() statt TimeoutExpired)
    - Stderr-Sammlung fuer Fehlerdiagnose

    B-116 Fix: ``cancel_check`` kann eine ``Callable[[], bool]`` sein.
    Wird in der Progress-Schleife UND vom Watchdog-Thread regelmaessig
    abgefragt; bei True wird der ffmpeg-Prozess terminiert und eine
    ``RuntimeError("Export abgebrochen")`` geworfen.
    """
    import threading

    # -progress pipe:1 einfuegen falls nicht vorhanden (fuer Progress-Parsing)
    if "-progress" not in cmd and progress_cb and total_duration > 0:
        # Nach "ffmpeg" und vor "-y" einfuegen
        idx = 1 if len(cmd) > 1 else 0
        cmd = cmd[:idx] + ["-progress", "pipe:1"] + cmd[idx:]

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
    cancelled = threading.Event()

    def _drain_stderr():
        for line in process.stderr:
            stderr_lines.append(line)

    stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
    stderr_thread.start()

    # B-116: Watchdog-Thread polled ``cancel_check`` auch wenn ffmpeg
    # keine stdout-Zeilen schreibt (z.B. bei laengeren Pre/Post-Phasen
    # oder wenn ``-progress`` nicht aktiv ist).
    cancel_watchdog = None
    if cancel_check is not None:
        def _cancel_watch():
            while process.poll() is None:
                try:
                    # B-170: nur einmal terminate() rufen — der Main-Loop
                    # kann denselben Cancel auch detektieren.
                    if cancel_check() and not cancelled.is_set():
                        cancelled.set()
                        process.terminate()
                        try:
                            process.wait(timeout=2.0)
                        except subprocess.TimeoutExpired:
                            process.kill()
                        return
                except Exception as exc:  # broad: watchdog must keep running
                    # B-167: log statt stumm sterben.
                    logger.warning(
                        "[Cancel-Watch] cancel_check raised: %s — Watchdog endet.", exc,
                    )
                    return
                time.sleep(0.2)
        cancel_watchdog = threading.Thread(target=_cancel_watch, daemon=True)
        cancel_watchdog.start()

    try:
        for line in process.stdout:
            # B-170: cancelled.is_set()-Guard verhindert Doppel-terminate
            # wenn Watchdog parallel denselben Cancel detected hat.
            if (
                cancel_check is not None
                and cancel_check()
                and not cancelled.is_set()
            ):
                cancelled.set()
                process.terminate()
                break
            line = line.strip()
            if not line:
                continue
            # Progress-Parsing: out_time_ms oder out_time
            if line.startswith("out_time_ms=") and total_duration > 0 and progress_cb:
                try:
                    time_us = int(line.split("=")[1])
                    current_sec = time_us / 1_000_000
                    pct = min(99, int(current_sec / total_duration * 100))
                    progress_cb(pct, f"Rendering {pct}%...")
                except (ValueError, IndexError) as e:
                    logger.warning("Parsing FFmpeg export out_time_ms progress: %s", e)
            elif line.startswith("out_time=") and total_duration > 0 and progress_cb:
                try:
                    time_str = line.split("=")[1]
                    parts = time_str.split(":")
                    if len(parts) == 3:
                        h, m, s = float(parts[0]), float(parts[1]), float(parts[2])
                        current_sec = h * 3600 + m * 60 + s
                        pct = min(99, int(current_sec / total_duration * 100))
                        progress_cb(pct, f"Rendering {pct}%...")
                except (ValueError, IndexError) as e:
                    logger.warning("Parsing FFmpeg export out_time progress: %s", e)

        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        stderr = ''.join(stderr_lines)
        raise RuntimeError(
            f"FFmpeg Timeout ({timeout}s). Stderr:\n{_sanitize_ffmpeg_error(stderr)}"
        )
    finally:
        if process.poll() is None:
            process.kill()
        stderr_thread.join(timeout=THREAD_JOIN_TIMEOUT_SEC)
        if cancel_watchdog is not None:
            cancel_watchdog.join(timeout=THREAD_JOIN_TIMEOUT_SEC)

    if cancelled.is_set():
        raise RuntimeError("Export abgebrochen (User-Cancel)")

    stderr = ''.join(stderr_lines)
    if process.returncode != 0:
        raise RuntimeError(f"FFmpeg fehlgeschlagen:\n{_sanitize_ffmpeg_error(stderr)}")


def export_preview(project_id: int = 1, resolution: str = "1920x1080",
                   fps: float = 30.0, duration_limit: float = 10.0,
                   progress_cb=None, cancel_check=None) -> str:
    """Rendert eine Vorschau der ersten N Sekunden der Timeline.

    Identisch zu export_timeline(), aber begrenzt auf duration_limit Sekunden.
    Gibt den Pfad zur temporaeren Preview-Datei zurueck.

    B-116: ``cancel_check`` siehe ``export_timeline``.
    """
    _cleanup_orphan_tempfiles()  # B-118
    # M-7 FIX: Use thread-safe clear function instead of direct dict access
    clear_probe_cache()
    try:
        w, h = resolution.split("x")
    except ValueError:
        raise ValueError(
            f"Ungueltige Aufloesung: '{resolution}'. Erwartet: WIDTHxHEIGHT"
        )

    preview_dir = _get_export_dir() / "previews"
    preview_dir.mkdir(parents=True, exist_ok=True)
    output_path = preview_dir / f"preview_{project_id}.mp4"

    with Session(engine) as session:
        entries = (
            session.query(TimelineEntry)
            .filter_by(project_id=project_id)
            .order_by(TimelineEntry.start_time)
            .all()
        )
        if not entries:
            raise ValueError("Keine Timeline-Eintraege zum Vorschau-Rendern vorhanden")

        video_entries = [e for e in entries if e.track == "video"]
        audio_entries = [e for e in entries if e.track == "audio"]

        _vid_ids = [ve.media_id for ve in video_entries]
        _clips_by_id = (
            {c.id: c for c in session.query(VideoClip).filter(
                VideoClip.id.in_(_vid_ids), VideoClip.deleted_at.is_(None)
            ).all()}
            if _vid_ids else {}
        )

        # Nur Segmente bis duration_limit aufnehmen
        video_segments = []
        for ve in video_entries:
            if ve.start_time >= duration_limit:
                break
            clip = _clips_by_id.get(ve.media_id)
            if not clip:
                continue
            source_start = ve.source_start or 0.0
            source_end = ve.source_end
            seg_duration = ve.end_time - ve.start_time if ve.end_time else (clip.duration or 10.0)
            source_duration = _source_duration_from_entry(
                ve, seg_duration, clip.duration
            )

            # Clip ggf. am Preview-Limit abschneiden
            end_time = ve.end_time or (ve.start_time + seg_duration)
            if end_time > duration_limit:
                trim = end_time - duration_limit
                source_duration = max(0.1, source_duration - trim)
                end_time = duration_limit

            video_segments.append({
                "path": clip.file_path,
                "start": ve.start_time,
                "end": end_time,
                "duration": clip.duration or 10.0,
                "source_start": source_start,
                "source_duration": source_duration,
                "crossfade": ve.crossfade_duration or 0.0,
                "brightness": ve.brightness or 0.0,
                "contrast": ve.contrast or 1.0,
            })

        audio_path = None
        if audio_entries:
            track = session.query(AudioTrack).filter(
                AudioTrack.id == audio_entries[0].media_id, AudioTrack.deleted_at.is_(None)
            ).first()
            if track:
                audio_path = track.file_path

    if not video_segments:
        raise ValueError("Keine Video-Clips auf der Timeline")

    total_steps = 5 if audio_path else 4
    has_effects = any(
        seg["crossfade"] > 0 or seg["brightness"] != 0.0 or seg["contrast"] != 1.0
        for seg in video_segments
    )

    if has_effects:
        return _export_with_filtergraph(
            video_segments, audio_path, output_path,
            w, h, fps, progress_cb, total_steps,
            cancel_check=cancel_check,
        )
    else:
        return _export_optimized_concat(
            video_segments, audio_path, output_path,
            w, h, fps, progress_cb, total_steps,
            cancel_check=cancel_check,
        )


def estimate_render_time(project_id: int = 1, resolution: str = "1920x1080",
                         fps: float = 30.0) -> dict:
    """Schaetzt die Renderzeit fuer den kompletten Timeline-Export.

    Returns:
        {
            "estimated_seconds": float,
            "estimated_label": str,       # z.B. "~2 Min 30 Sek"
            "total_duration": float,      # Timeline-Dauer in Sekunden
            "segment_count": int,
            "has_effects": bool,
            "preset_summary": str,        # z.B. "1920x1080 @ 30fps"
        }
    """
    summary = get_timeline_summary(project_id)
    total_dur = summary["estimated_duration"]
    seg_count = summary["video_clips"]

    if seg_count == 0 or total_dur <= 0:
        return {
            "estimated_seconds": 0.0,
            "estimated_label": "Keine Clips",
            "total_duration": 0.0,
            "segment_count": 0,
            "has_effects": False,
            "preset_summary": f"{resolution} @ {fps:.0f}fps",
        }

    # Heuristik: Renderzeit basierend auf Segment-Anzahl, Aufloesung und Effekten
    # Basis: ~0.5s pro Sekunde Video bei 1080p (H.264 fast preset)
    try:
        w, h = resolution.split("x")
        pixel_factor = (int(w) * int(h)) / (1920 * 1080)
    except (ValueError, ZeroDivisionError):
        pixel_factor = 1.0

    # Pruefen ob Effekte vorhanden sind (vereinfachte Pruefung via DB)
    has_effects = False
    with Session(engine) as session:
        entries = (
            session.query(TimelineEntry)
            .filter_by(project_id=project_id, track="video")
            .all()
        )
        has_effects = any(
            (e.crossfade_duration or 0) > 0
            or (e.brightness or 0) != 0
            or (e.contrast or 1.0) != 1.0
            for e in entries
        )

    base_time_per_sec = 0.5 * pixel_factor
    if has_effects:
        base_time_per_sec *= 1.8  # Filtergraph ~80% langsamer
    # Overhead pro Segment (Preprocessing)
    segment_overhead = seg_count * 0.3

    estimated = total_dur * base_time_per_sec + segment_overhead

    # Label formatieren
    if estimated < 60:
        label = f"~{estimated:.0f} Sek"
    elif estimated < 3600:
        mins = int(estimated // 60)
        secs = int(estimated % 60)
        label = f"~{mins} Min {secs} Sek"
    else:
        hours = int(estimated // 3600)
        mins = int((estimated % 3600) // 60)
        label = f"~{hours} Std {mins} Min"

    return {
        "estimated_seconds": round(estimated, 1),
        "estimated_label": label,
        "total_duration": total_dur,
        "segment_count": seg_count,
        "has_effects": has_effects,
        "preset_summary": f"{resolution} @ {fps:.0f}fps",
    }


def get_timeline_summary(project_id: int = 1) -> dict:
    with Session(engine) as session:
        entries = (
            session.query(TimelineEntry)
            .filter_by(project_id=project_id)
            .all()
        )
        video_count = sum(1 for e in entries if e.track == "video")
        audio_count = sum(1 for e in entries if e.track == "audio")
        total_duration = 0.0
        for e in entries:
            if e.track == "video" and e.end_time:
                total_duration = max(total_duration, e.end_time)
        return {
            "video_clips": video_count,
            "audio_tracks": audio_count,
            "total_entries": len(entries),
            "estimated_duration": total_duration,
        }
