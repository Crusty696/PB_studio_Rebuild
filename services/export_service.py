"""Export-Service: Fuegt Timeline-Clips via FFmpeg zu einem finalen Video zusammen.

Phase 3 Erweiterung: Crossfades, Farbkorrektur, Stem-Mix, Auto-Ducking.
Optimiert fuer viele kleine Segmente (Auto-Edit to Beat).
"""

import json as _json
import logging
import subprocess
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
from services.ffmpeg_utils import parse_frame_rate, probe_duration, subprocess_kwargs
from services.startup_checks import get_ffmpeg_bin, get_ffprobe_bin
from services.nvenc_policy import require_nvenc, required_message
from services.ffmpeg_utils import sanitize_ffmpeg_error as _sanitize_ffmpeg_error

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
    try:
        from services.convert_service import detect_nvenc
        nvenc_available = bool(detect_nvenc().get("h264_nvenc"))
    except Exception:
        nvenc_available = False

    if nvenc_available:
        return ["-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr",
                "-cq", "18", "-b:v", "15M"]

    logger.warning("NVENC (h264_nvenc) nicht verfuegbar! Timeline-Export weicht auf CPU (libx264) aus.")

    if require_nvenc():
        raise RuntimeError(
            required_message("h264_nvenc nicht verfuegbar; Export-CPU-Fallback verboten")
        )
    return ["-c:v", "libx264", "-preset", "fast", "-crf", "23"]


logger = logging.getLogger(__name__)


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


# B-504: Ziel-Pixelformat der standardisierten Segmente. Sowohl libx264
# (CRF-Preset) als auch h264_nvenc erzeugen bei 8-bit-Input per Default
# yuv420p — abweichende Quellen (yuv444p, yuv420p10le, yuvj420p, ...)
# wuerden beim Concat-Stream-Copy einen inkonsistenten Stream ergeben.
_CONCAT_TARGET_PIX_FMT = "yuv420p"


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
        # B-611: source_end wird beim Pacing auf 4 Dezimalen gerundet; ein
        # Ueberschuss im ms-Bereich ist Rundung, KEIN Datenfehler. Frueher
        # warf schon ein 33-us-Ueberschuss (1e-6-Toleranz) hier ValueError und
        # brach den GESAMTEN Export ab. Jetzt: kleinen Ueberschuss auf die
        # echte Clip-Laenge clampen (ffmpeg liest bis Clip-Ende), nur einen
        # GROBEN Ueberschuss (echte Korruption) weiterhin als Fehler werfen.
        # Wirkt auch fuer bestehende Timelines mit bereits hochgerundeten
        # source_end-Werten (kein Neu-Rendern noetig).
        ROUNDING_TOLERANCE_SEC = 0.05  # 50ms — deckt 4-Dezimal-Rundung + Frame-Grenzen
        if source_end_abs > clip_duration + ROUNDING_TOLERANCE_SEC:
            raise ValueError(
                f"Source-Bereich fuer TimelineEntry {getattr(entry, 'id', '?')} "
                f"ueberschreitet clip duration {clip_duration:.3f}s"
            )
        if source_end_abs > clip_duration:
            source_duration = max(0.0, clip_duration - source_start)
    return source_duration


def _prepare_audio_entry_for_timeline(
    audio_path: str,
    entry,
    track_duration: float | None,
    temp_files: list,
    cancel_check=None,
) -> str:
    timeline_start = float(entry.start_time or 0.0)
    if timeline_start < 0:
        raise ValueError(
            f"Ungueltiger Audio-Timeline-Start fuer TimelineEntry "
            f"{getattr(entry, 'id', '?')}: {timeline_start:.3f}s"
        )

    fallback_duration = (
        float(entry.end_time) - timeline_start
        if getattr(entry, "end_time", None) is not None
        else float(track_duration or 0.0)
    )
    source_duration = _source_duration_from_entry(
        entry, fallback_duration, track_duration
    )
    source_start = float(entry.source_start or 0.0)
    source_end = getattr(entry, "source_end", None)
    needs_prepare = (
        timeline_start > 0.001
        or source_start > 0.001
        or source_end is not None
    )
    if not needs_prepare:
        return audio_path

    tmp = tempfile.NamedTemporaryFile(
        suffix=".wav", delete=False, prefix="pb_audio_entry_"
    )
    tmp.close()
    temp_files.append(tmp.name)

    cmd = [
        FFMPEG, "-y",
        "-ss", f"{source_start:.3f}",
        "-i", audio_path,
        "-t", f"{source_duration:.3f}",
        "-vn",
    ]
    delay_ms = int(round(timeline_start * 1000.0))
    if delay_ms > 0:
        cmd += ["-af", f"adelay={delay_ms}:all=1"]
    cmd += ["-ar", "48000", "-c:a", "pcm_s24le", tmp.name]
    _run_ffmpeg(
        cmd, timeout=FFMPEG_RENDER_TIMEOUT_SEC, cancel_check=cancel_check
    )
    return tmp.name


def _validate_video_timeline_gaps(
    video_segments: list[dict],
    epsilon: float = 0.01,
    close_threshold: float = 0.05,
) -> None:
    """Prueft die Video-Timeline auf Luecken und SCHLIESST kleine automatisch.

    B-613: Eine winzige Luecke (z.B. 35ms durch 4-Dezimal-Rundung oder den
    Onset-Snap ±50ms) liess frueher den GESAMTEN Export mit ValueError
    abbrechen (Concat/Filtergraph ist gegen so kleine Luecken unempfindlich —
    35ms = imperceptibler A/V-Versatz). Jetzt: Luecken bis ``close_threshold``
    (50ms) werden geschlossen, indem das betroffene Segment um die
    Lueckenbreite nach vorne geschoben wird (Dauer bleibt, Anschluss wird
    lueckenlos). NUR echte, grosse Luecken (> close_threshold, = fehlendes
    Material) werfen weiterhin — die sind ein echter Desync-Fehler.
    Gleiche Robustheits-Philosophie wie B-611.
    """
    previous_end = 0.0
    for index, segment in enumerate(video_segments):
        start = float(segment["start"])
        end = float(segment["end"])
        gap = start - previous_end
        if gap > epsilon:
            if gap <= close_threshold:
                # Kleine Luecke -> Segment zurueckschieben (Dauer erhalten).
                duration = end - start
                segment["start"] = previous_end
                segment["end"] = previous_end + duration
                start = segment["start"]
                end = segment["end"]
                logger.warning(
                    "B-613: kleine Timeline-Luecke %.3fs vor Video-Segment %d "
                    "geschlossen (Segment um %.3fs zurueckgeschoben).",
                    gap, index + 1, gap,
                )
            else:
                raise ValueError(
                    f"Timeline gap vor Video-Segment {index + 1}: "
                    f"{previous_end:.3f}s bis {start:.3f}s"
                )
        previous_end = max(previous_end, end)


def _cleanup_orphan_tempfiles(max_age_hours: float = 1.0) -> int:
    """B-118/B-400: entfernt zurueckgelassene Export-Tempfiles
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
        for pattern in (
            "pb_std_*",
            "pb_lufs_*",
            "pb_audio_entry_*",
            "pb_concat_*",
            "pb_fcs_*",
        ):
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
        logger.info("B-118/B-400: %d orphan export tempfile(s) entfernt.", deleted)
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
    try:
        return probe_duration(
            audio_path, fallback=0.0, timeout=10, ffprobe_bin=ffprobe_bin,
        )
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
        _missing_clip_count = 0
        for ve in video_entries:
            clip = _clips_by_id.get(ve.media_id)
            if not clip:
                # B-580: media_id ist kein FK (D-028) — ein soft-geloeschter
                # oder fehlender VideoClip wuerde sonst still aus dem Export
                # fallen. Sichtbar machen, aber Export NICHT abbrechen.
                _missing_clip_count += 1
                logger.warning(
                    "Timeline-Eintrag %s referenziert fehlenden/soft-geloeschten "
                    "VideoClip media_id=%s — Segment wird NICHT exportiert",
                    getattr(ve, "id", "?"), ve.media_id,
                )
                continue
            if clip:
                source_start = ve.source_start or 0.0
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

        if _missing_clip_count:
            # B-580: zusammenfassende Warnung, damit der Datenverlust nicht
            # in vielen Einzelzeilen untergeht.
            logger.warning(
                "Export: %d von %d Video-Timeline-Eintraegen referenzieren "
                "fehlende/soft-geloeschte VideoClips und wurden NICHT exportiert",
                _missing_clip_count, len(video_entries),
            )

        audio_source = None
        if audio_entries:
            audio_entry = audio_entries[0]
            track = session.query(AudioTrack).filter(
                AudioTrack.id == audio_entry.media_id, AudioTrack.deleted_at.is_(None)
            ).first()
            if track:
                audio_source = (track.file_path, audio_entry, track.duration)

    if not video_segments:
        raise ValueError("Keine Video-Clips auf der Timeline")
    _validate_video_timeline_gaps(video_segments)

    audio_temp_files = []
    audio_path = None
    if audio_source:
        audio_path = _prepare_audio_entry_for_timeline(
            audio_source[0],
            audio_source[1],
            audio_source[2],
            audio_temp_files,
            cancel_check=cancel_check,
        )

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
            extra_temp_files=audio_temp_files,
        )
    else:
        return _export_optimized_concat(
            video_segments, audio_path, output_path,
            w, h, fps, progress_cb, total_steps,
            cancel_check=cancel_check,
            extra_temp_files=audio_temp_files,
        )


def _export_optimized_concat(video_segments, audio_path, output_path,
                              w, h, fps, progress_cb, total_steps,
                              cancel_check=None, extra_temp_files=None):
    """Concat-Export mit automatischer Vorverarbeitung nicht-konformer Clips.

    PERF-FIX: Clips die nicht target-konform sind (andere Aufloesung/FPS/Codec)
    werden VOR dem Concat einzeln standardisiert. Dadurch kann der Concat-Schritt
    ohne den schweren scale/pad/fps-Filter laufen → massiv schneller.
    Clips die bereits konform sind werden direkt concat-kopiert.
    """
    step = 0
    temp_files = list(extra_temp_files or [])
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
                # B-504: `duration` allein trimmt im concat-Demuxer NICHT —
                # ist das Timeline-Segment kuerzer als der Quellclip, liefe
                # der ganze Clip rein und die Audio-Sync kippt. Daher bei
                # kuerzerem Segment explizit inpoint/outpoint schreiben.
                clip_duration = _get_probed_info(seg["path"]).get("duration", 0.0)
                if clip_duration > 0.0 and source_duration < clip_duration - 0.05:
                    processed_segments.append({
                        "path": seg["path"],
                        "duration": source_duration,
                        "inpoint": 0.0,
                        "outpoint": source_duration,
                    })
                else:
                    processed_segments.append({
                        "path": seg["path"],
                        "duration": source_duration,
                        "inpoint": None,
                        "outpoint": None,
                    })

        # Concat-Datei erstellen
        # B-504: encoding="utf-8" zwingend — FFmpeg liest die Concat-Liste
        # als UTF-8; ohne explizites encoding schreibt Windows cp1252 und
        # Umlaut-/Unicode-Pfade zerbrechen (vgl. pb_fcs_-Tempfile unten).
        concat_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, prefix="pb_concat_",
            encoding="utf-8",
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
                             cancel_check=None, extra_temp_files=None):
    """Komplexer Export mit Filtergraph (Crossfades + Farbkorrektur)."""
    step = 0
    temp_files = list(extra_temp_files or [])

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
    kwargs: dict = subprocess_kwargs()

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

    timeout_error: subprocess.TimeoutExpired | None = None
    try:
        if reader is not None:
            # stdout wird im Reader-Thread gelesen — wir warten nur auf stderr.
            try:
                _, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                process.kill()
                _, stderr = process.communicate()
                timeout_error = exc
            reader.join(timeout=THREAD_JOIN_TIMEOUT_SEC)
            stdout = "".join(stdout_lines)
        else:
            try:
                stdout, stderr = process.communicate(timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                process.kill()
                stdout, stderr = process.communicate()
                timeout_error = exc
    finally:
        watchdog.join(timeout=THREAD_JOIN_TIMEOUT_SEC)

    if cancelled.is_set():
        raise RuntimeError("LUFS-Normalisierung abgebrochen (User-Cancel)")
    if timeout_error is not None:
        raise subprocess.TimeoutExpired(
            cmd=cmd,
            timeout=timeout,
            output=stdout,
            stderr=stderr,
        )

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
    except subprocess.TimeoutExpired as e:
        raise RuntimeError(f"LUFS-Normalisierung Timeout nach {e.timeout}s") from e
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
        from services.brain.gpu_serializer import get_default_serializer
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
                # B-467: FFmpeg schreibt im ersten Progress-Frame oft
                # ``out_time_ms=N/A`` (noch kein Output). Das ist kein Fehler —
                # ueberspringen statt eine WARNING zu loggen.
                raw = line.split("=", 1)[1].strip()
                if raw and raw != "N/A":
                    try:
                        time_us = int(raw)
                        current_sec = time_us / 1_000_000
                        pct = min(99, int(current_sec / total_duration * 100))
                        progress_cb(pct, f"Rendering {pct}%...")
                    except (ValueError, IndexError) as e:
                        logger.warning("Parsing FFmpeg export out_time_ms progress: %s", e)
            elif line.startswith("out_time=") and total_duration > 0 and progress_cb:
                # B-467: gleiche N/A-Behandlung fuer den out_time-Branch.
                time_str = line.split("=", 1)[1].strip()
                if time_str and time_str != "N/A":
                    try:
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

        # B-332: Das Preview-Fenster war fix [0, duration_limit] in Timeline-
        # Koordinaten. Wenn der erste Video-Clip aber erst nach duration_limit
        # beginnt (z.B. 10.322s bei 10s-Limit), blieb video_segments leer und
        # der Export crashte mit "Keine Video-Clips auf der Timeline", obwohl
        # die Timeline Video-Clips hat. Fix: das Fenster am ersten Video-Clip
        # verankern -> [window_start, window_start + duration_limit].
        window_start = video_entries[0].start_time if video_entries else 0.0
        window_end = window_start + duration_limit

        # Nur Segmente bis window_end aufnehmen
        video_segments = []
        _missing_clip_count = 0
        for ve in video_entries:
            if ve.start_time >= window_end:
                break
            clip = _clips_by_id.get(ve.media_id)
            if not clip:
                # B-580: fehlender/soft-geloeschter Clip nicht still verwerfen.
                _missing_clip_count += 1
                logger.warning(
                    "Timeline-Eintrag %s referenziert fehlenden/soft-geloeschten "
                    "VideoClip media_id=%s — Segment wird NICHT exportiert",
                    getattr(ve, "id", "?"), ve.media_id,
                )
                continue
            source_start = ve.source_start or 0.0
            seg_duration = ve.end_time - ve.start_time if ve.end_time else (clip.duration or 10.0)
            source_duration = _source_duration_from_entry(
                ve, seg_duration, clip.duration
            )

            # Clip ggf. am Preview-Fensterende abschneiden
            end_time = ve.end_time or (ve.start_time + seg_duration)
            if end_time > window_end:
                trim = end_time - window_end
                source_duration = max(0.1, source_duration - trim)
                end_time = window_end

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

        if _missing_clip_count:
            logger.warning(
                "Preview: %d Video-Timeline-Eintraege referenzieren "
                "fehlende/soft-geloeschte VideoClips und wurden NICHT gerendert",
                _missing_clip_count,
            )

        audio_source = None
        if audio_entries:
            audio_entry = audio_entries[0]
            track = session.query(AudioTrack).filter(
                AudioTrack.id == audio_entry.media_id, AudioTrack.deleted_at.is_(None)
            ).first()
            if track:
                audio_source = (track.file_path, audio_entry, track.duration)

    if not video_segments:
        raise ValueError("Keine Video-Clips auf der Timeline")

    audio_temp_files = []
    audio_path = None
    if audio_source:
        audio_path = _prepare_audio_entry_for_timeline(
            audio_source[0],
            audio_source[1],
            audio_source[2],
            audio_temp_files,
            cancel_check=cancel_check,
        )

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
            extra_temp_files=audio_temp_files,
        )
    else:
        return _export_optimized_concat(
            video_segments, audio_path, output_path,
            w, h, fps, progress_cb, total_steps,
            cancel_check=cancel_check,
            extra_temp_files=audio_temp_files,
        )


def estimate_render_time(project_id: int = 1, resolution: str = "1920x1080",
                         fps: float = 30.0, summary: dict | None = None) -> dict:
    """Schaetzt die Renderzeit fuer den kompletten Timeline-Export.

    Args:
        summary: optional bereits geladenes ``get_timeline_summary``-Ergebnis
            (virt-M4-Fix: der _ProductionInfoWorker rief die Summary sonst
            doppelt — zweimal derselbe Timeline-Scan pro EXPORT-Klick).

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
    if summary is None:
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

    # Pruefen ob Effekte vorhanden sind (vereinfachte Pruefung via DB).
    # virt-M4-Fix: Spalten-Query statt Voll-ORM-Load (TimelineEntry.anchors
    # ist lazy='selectin' — der Voll-Load zog alle ClipAnchors mit).
    has_effects = False
    with Session(engine) as session:
        effect_rows = (
            session.query(
                TimelineEntry.crossfade_duration,
                TimelineEntry.brightness,
                TimelineEntry.contrast,
            )
            .filter_by(project_id=project_id, track="video")
            .all()
        )
        has_effects = any(
            (cf or 0) > 0
            or (br or 0) != 0
            or (ct or 1.0) != 1.0
            for cf, br, ct in effect_rows
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
    """Zaehlt exportierbare Timeline-Eintraege + max. Video-Endzeit.

    virt-M4-Fix 2026-07-10 (Watchdog-Beweis workspace_switch_perf Lauf 2):
    Vorher Voll-ORM-Loads — ``query(TimelineEntry).all()`` zog via
    lazy='selectin' ALLE ClipAnchors nach, ``query(VideoClip).all()`` alle
    Scenes, ``query(AudioTrack).all()`` die Waveform-/Beatgrid-Blobs
    (lazy='joined'). Bei 1429 Entries/375 Clips lief die Query minutenlang
    (Stack: _load_via_parent) und verstopfte die DB — Main-Thread-Queries
    (get_cut_list & Co.) hingen im busy_timeout => 25-32s-Klick-Freezes.
    Jetzt reine Spalten-Queries: keine Relationship-Loads, nur Tupel.
    """
    with Session(engine) as session:
        rows = (
            session.query(
                TimelineEntry.media_id,
                TimelineEntry.track,
                TimelineEntry.end_time,
            )
            .filter_by(project_id=project_id)
            .all()
        )
        video_ids = [m for m, t, _ in rows if t == "video"]
        audio_ids = [m for m, t, _ in rows if t == "audio"]
        active_video_ids = (
            {
                r[0] for r in session.query(VideoClip.id).filter(
                    VideoClip.id.in_(video_ids), VideoClip.deleted_at.is_(None)
                ).all()
            }
            if video_ids else set()
        )
        active_audio_ids = (
            {
                r[0] for r in session.query(AudioTrack.id).filter(
                    AudioTrack.id.in_(audio_ids), AudioTrack.deleted_at.is_(None)
                ).all()
            }
            if audio_ids else set()
        )
        exportable = [
            (m, t, e) for m, t, e in rows
            if (
                (t == "video" and m in active_video_ids)
                or (t == "audio" and m in active_audio_ids)
            )
        ]
        video_count = sum(1 for _, t, _e in exportable if t == "video")
        audio_count = sum(1 for _, t, _e in exportable if t == "audio")
        total_duration = 0.0
        for _, t, end_time in exportable:
            if t == "video" and end_time:
                total_duration = max(total_duration, end_time)
        return {
            "video_clips": video_count,
            "audio_tracks": audio_count,
            "total_entries": len(exportable),
            "estimated_duration": total_duration,
        }
