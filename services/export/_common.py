"""AUFRAEUM B2 — geteilte Konstanten + Leaf-Helper des Export-Service.

Reiner Verbatim-Code-Move aus ``services/export_service.py`` (kein
Logik-Change). Enthaelt FFmpeg-Pfade, Pfad-/Validierungs-Helper und
Tempfile-Cleanup. Der ``logger`` behaelt bewusst den Namen
``services.export_service``, damit Log-Routing/caplog-Tests byte-gleich
bleiben.
"""

import logging
from pathlib import Path, PurePosixPath, PureWindowsPath

from services.startup_checks import get_ffmpeg_bin, get_ffprobe_bin

logger = logging.getLogger("services.export_service")

# FIX-1.2: FFmpeg-Pfad konfigurierbar (identisch mit convert_service.py)
FFMPEG = get_ffmpeg_bin()
FFPROBE = get_ffprobe_bin()


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


# B-504: Ziel-Pixelformat der standardisierten Segmente. Sowohl libx264
# (CRF-Preset) als auch h264_nvenc erzeugen bei 8-bit-Input per Default
# yuv420p — abweichende Quellen (yuv444p, yuv420p10le, yuvj420p, ...)
# wuerden beim Concat-Stream-Copy einen inkonsistenten Stream ergeben.
_CONCAT_TARGET_PIX_FMT = "yuv420p"


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
