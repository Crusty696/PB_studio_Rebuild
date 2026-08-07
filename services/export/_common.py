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


# B-769: EINE gemeinsame Quelle fuer die Gap-Toleranzen von Export-Validator
# (hier) und Timeline-Repair (services/timeline_service.py). Vorher hatte der
# Repair eigene Schwellen (1e-3) und uebersprang locked Rows — er liess damit
# Luecken durch, die der Validator ablehnt, und der Export brach Minuten
# spaeter mit ValueError ab.
TIMELINE_GAP_EPSILON_SEC = 0.01
TIMELINE_GAP_CLOSE_THRESHOLD_SEC = 0.05


def heal_video_timeline_gaps(
    items: list[dict],
    epsilon: float = TIMELINE_GAP_EPSILON_SEC,
) -> dict:
    """B-769 Kernlogik: schliesst Video-Timeline-Luecken IN-MEMORY (pure,
    kein DB-Zugriff). Wird von ZWEI Pfaden genutzt:

    - ``repair_timeline_integrity`` (services/timeline_service.py): legitimer
      DB-Schreibpfad nach Auto-Edit-Apply — mappt ORM-Rows auf dicts, ruft
      diese Funktion, schreibt Ergebnis zurueck.
    - ``export_timeline`` (services/export_service.py): heilt NUR die geladene
      Segmentliste fuer das Rendering — die DB bleibt byte-identisch (Export
      darf das Projekt nicht mutieren; Consulting-Review 2026-08-07).

    ``items``: dicts mit ``start``/``end`` (Pflicht) sowie optional
    ``locked``, ``source_end``, ``source_duration``, ``clip_duration``.
    Reihenfolge = Timeline-Reihenfolge (nach start sortiert).

    Vertrag: LOCKED Eintraege werden NIE verschoben oder veraendert.
    Pass 1 kompaktiert unlocked Eintraege nach links (locked = Anker).
    Pass 2 fuellt verbleibende Luecken VOR locked Ankern, indem vorangehende
    unlocked Eintraege um ungenutztes Quellmaterial
    (``clip_duration - source_end``) verlaengert und dazwischenliegende
    Eintraege nach rechts geschoben werden.

    Rueckgabe: ``{"gaps_closed": int, "unclosable": [(prev_end, start), ...]}``
    — ``unclosable`` sind Luecken, die ohne Lock-Bruch nicht schliessbar sind
    (z.B. Luecke direkt zwischen zwei gelockten Segmenten oder kein
    Restmaterial in allen Vorgaenger-Clips).
    """
    gaps_closed = 0
    unclosable: list[tuple[float, float]] = []

    # Pass 1: unlocked nach links kompaktieren, locked bleibt Anker.
    cursor = 0.0
    for it in items:
        start = float(it["start"])
        end = float(it["end"])
        if not it.get("locked") and start > cursor + epsilon:
            duration = max(0.0, end - start)
            it["start"] = round(cursor, 4)
            it["end"] = round(it["start"] + duration, 4)
            gaps_closed += 1
        cursor = max(cursor, float(it["end"]))

    # Pass 2: Luecken vor locked Ankern mit Restmaterial fuellen.
    #
    # F-1 (adversarialer Review 2026-08-07): Der fruehere Backfill setzte
    # POSITIONELL bei idx-1 an. Bei einer Overlap-Insel (z.B. [0..10],
    # [2..4], locked [12..14]) verlaengerte er die Insel (4->6), obwohl das
    # reale prev_end 10.0 vom ERSTEN Segment kommt — die Luecke 10->12 blieb
    # offen, wurde aber als gaps_closed gemeldet und der Validator warf
    # spaeter den rohen ValueError. Fix: Kandidaten in END-Reihenfolge
    # (zuerst das Segment mit dem MAXIMALEN end, das prev_end definiert),
    # und der Erfolg wird IMMER gegen das REALE prev_end verifiziert —
    # nie "geschlossen aber offen" melden.
    prev_end = 0.0
    for idx, it in enumerate(items):
        start = float(it["start"])
        gap = start - prev_end
        if it.get("locked") and gap > epsilon:
            # Fenster: unlocked Items zwischen vorherigem Anker und idx.
            window: list[int] = []
            j = idx - 1
            while j >= 0 and not items[j].get("locked"):
                window.append(j)
                j -= 1
            # Kandidaten nach end absteigend: zuerst das Segment, dessen
            # Verlaengerung das reale prev_end tatsaechlich anhebt.
            order = sorted(
                window, key=lambda k: float(items[k]["end"]), reverse=True
            )
            remaining = gap
            for c in order:
                if remaining <= epsilon:
                    break
                prev = items[c]
                spare = 0.0
                clip_duration = prev.get("clip_duration")
                source_end = prev.get("source_end")
                if clip_duration and source_end is not None:
                    spare = float(clip_duration) - float(source_end)
                take = min(spare, remaining)
                if take <= 1e-9:
                    continue
                c_end_pre = float(prev["end"])
                prev["end"] = round(c_end_pre + take, 4)
                prev["source_end"] = round(float(source_end) + take, 4)
                if prev.get("source_duration") is not None:
                    prev["source_duration"] = round(
                        float(prev["source_duration"]) + take, 4
                    )
                # Fenster-Items mit GROESSEREM end nach rechts schieben,
                # damit die Kette bis zum Anker geschlossen bleibt (bei
                # kontiguierlichen Timelines identisch zum alten Verhalten;
                # Overlap-Inseln mit kleinerem end bleiben unangetastet).
                for k in window:
                    other = items[k]
                    if k != c and float(other["end"]) > c_end_pre:
                        other["start"] = round(float(other["start"]) + take, 4)
                        other["end"] = round(float(other["end"]) + take, 4)
                remaining -= take
            # F-1: Erfolg gegen das REALE prev_end (max end aller Items vor
            # dem Anker) verifizieren — ehrliches Reporting: entweder
            # wirklich geschlossen ODER unclosable, nie beides falsch.
            real_prev_end = max(
                (float(x["end"]) for x in items[:idx]), default=0.0
            )
            if start - real_prev_end <= epsilon:
                gaps_closed += 1
            else:
                unclosable.append((round(real_prev_end, 4), round(start, 4)))
            prev_end = max(prev_end, real_prev_end)
        prev_end = max(prev_end, float(it["end"]))

    return {"gaps_closed": gaps_closed, "unclosable": unclosable}


def _validate_video_timeline_gaps(
    video_segments: list[dict],
    epsilon: float = TIMELINE_GAP_EPSILON_SEC,
    close_threshold: float = TIMELINE_GAP_CLOSE_THRESHOLD_SEC,
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
