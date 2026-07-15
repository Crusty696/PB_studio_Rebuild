"""OTIO Timeline Service: Ersetzt die interne Timeline-Logik durch OpenTimelineIO.

Phase 1 Foundation — SEKTOR 2.
PoC-Erkenntnis R2: OTIO-Marker serialisieren Python-Listen als AnyVector.
Konvertierungsfunktion list() MUSS vor Zugriff auf audio_features aufgerufen werden.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

import opentimelineio as otio

logger = logging.getLogger(__name__)
from opentimelineio.opentime import RationalTime, TimeRange

from database import get_active_project_id
# engine: im Modul-Code nicht direkt aufgerufen, aber Teil der patchbaren
# Oberflaeche — Tests monkeypatchen services.timeline_service.engine.
# Nicht per ruff F401 entfernen.
from database import engine  # noqa: F401
from database import TimelineEntry
from sqlalchemy import select  # B-090: column-select statt Blob-Voll-Load

# M-12 Fix: Thread-safe lock for timeline writes to prevent data races
_timeline_write_lock = threading.Lock()

def _get_exports_dir() -> Path:
    """Return exports directory for the current project (lazy APP_ROOT read).

    BUG-FIX: Was module-level constant that became stale after set_project().
    Now reads APP_ROOT at call time so project switches are respected.
    """
    import database.session as _session
    return _session.APP_ROOT / "exports"

# PB Studio namespace in OTIO metadata
PB_NS = "pb_studio"


def plan_video_timeline_add(
    project_id: int,
    video_ids: list[int],
    *,
    audio_id_hint: int | None = None,
    allow_duplicates: bool | None = None,
) -> dict:
    """Fixplan 2026-07-07 Schritt 7b: Budget-Plan fuer das Einfuegen von
    Video-Clips in die Timeline.

    User-Regel (V3): Die Audio-Datei gibt die Laenge vor — es duerfen nur so
    viele Clips in die Timeline uebergeben werden, wie das Audio braucht.
    Vorher appendete der Add-Pfad unbegrenzt (real: 2x 39 Clips -> 137 Clips,
    1003 s Timeline bei 308 s Audio) und ohne Duplikat-Schutz.

    Regeln:
    * Budget = Dauer des Audio-Tracks auf der Timeline; sonst
      ``audio_id_hint`` (Audio, das im selben Vorgang hinzugefuegt wird);
      ohne beides wird ein Bulk-Add (>1 Clip) blockiert (Einzel-Add erlaubt).
    * Angenommen wird, solange der Startpunkt des Clips vor dem Budget-Ende
      liegt (der letzte Clip darf ueberstehen — Render endet am Audio).
    * Duplikat-Schutz nur bei Bulk-Add (>1 Clip); Einzel-Add darf bewusst
      duplizieren. Ueberschreibbar via ``allow_duplicates``.

    Returns dict:
        accepted:          list[{media_id, title, duration, start_time}]
        skipped_duplicate: list[int]
        skipped_budget:    list[int]
        budget:            float | None  (Sekunden)
        video_start:       float  (Ende der bestehenden Video-Spur)
        blocked_reason:    str | None  (gesetzt -> nichts einfuegen)
    """
    from database import AudioTrack, VideoClip, nullpool_session

    result: dict = {
        "accepted": [], "skipped_duplicate": [], "skipped_budget": [],
        "budget": None, "video_start": 0.0, "blocked_reason": None,
    }
    if not video_ids:
        return result

    is_bulk = len(video_ids) > 1
    dedup = is_bulk if allow_duplicates is None else not allow_duplicates

    with nullpool_session() as session:
        # Bestehende Video-Spur: Ende + bereits verwendete media_ids
        rows = session.query(
            TimelineEntry.media_id, TimelineEntry.end_time,
        ).filter_by(project_id=project_id, track="video").all()
        existing_ids = {int(r[0]) for r in rows if r[0] is not None}
        video_start = max(
            (float(r[1]) for r in rows if r[1] is not None), default=0.0)
        result["video_start"] = video_start

        # Budget-Referenz: Audio auf Timeline > audio_id_hint > None
        budget = None
        audio_row = (
            session.query(TimelineEntry.media_id)
            .filter_by(project_id=project_id, track="audio")
            .first()
        )
        ref_audio_id = int(audio_row[0]) if audio_row and audio_row[0] else audio_id_hint
        if ref_audio_id is not None:
            # B-090: column-select statt ORM-Voll-Laden (waveform_data/beatgrid joined); nutzt nur duration
            track = session.execute(
                select(AudioTrack.duration).where(AudioTrack.id == ref_audio_id)
            ).first()
            if track is not None and track.duration:
                budget = float(track.duration)
        result["budget"] = budget

        if budget is None and is_bulk:
            result["blocked_reason"] = (
                "Kein Audio-Track als Laengen-Referenz vorhanden. Zuerst "
                "Audio zur Timeline hinzufuegen (oder mit-markieren) — die "
                "Audio-Datei gibt die Timeline-Laenge vor."
            )
            return result

        for vid in video_ids:
            vid = int(vid)
            if dedup and (vid in existing_ids
                          or any(a["media_id"] == vid for a in result["accepted"])):
                result["skipped_duplicate"].append(vid)
                continue
            if budget is not None and video_start >= budget - 0.01:
                result["skipped_budget"].append(vid)
                continue
            # B-090: column-select statt ORM-Voll-Laden (scenes/audio_video_anchors selectin); nutzt nur duration, file_path
            clip = session.execute(
                select(VideoClip.duration, VideoClip.file_path).where(VideoClip.id == vid)
            ).first()
            if clip is None:
                continue
            duration = float(clip.duration or 10.0)
            title = Path(clip.file_path).stem if clip.file_path else f"Video #{vid}"
            result["accepted"].append({
                "media_id": vid, "title": title,
                "duration": duration, "start_time": video_start,
            })
            video_start += duration

    logger.info(
        "plan_video_timeline_add: %d angefragt -> %d akzeptiert, "
        "%d Duplikate, %d ueber Budget (budget=%s, start=%.1fs)",
        len(video_ids), len(result["accepted"]),
        len(result["skipped_duplicate"]), len(result["skipped_budget"]),
        f"{budget:.1f}s" if budget is not None else "None",
        result["video_start"],
    )
    return result


def apply_auto_edit_segments(segments: list[dict], project_id: int | None = None,
                             max_retries: int = 5) -> int:
    """Ersetzt alle Video-Timeline-Eintraege durch neue Auto-Edit Segmente.

    Atomar: DELETE + INSERT in einer einzigen Transaktion.
    Verwendet eine eigene NullPool-Engine um DB-Lock durch verwaiste
    Pool-Connections anderer Worker zu umgehen.

    M-12 Fix: Thread-safe with lock to prevent data races on concurrent calls.
    Returns: Anzahl der eingefuegten Eintraege.
    """
    import time as _time
    from sqlalchemy.exc import OperationalError

    if project_id is None:
        project_id = get_active_project_id()

    # M-12 Fix: Acquire lock to serialize timeline writes and prevent race conditions
    with _timeline_write_lock:
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    # H-15 FIX: Don't dispose shared engine in retry loop — just wait
                    _time.sleep(1)
                inserted = _do_apply_segments(segments, project_id)
                repair_timeline_integrity(project_id)
                # NEUBAU-VOLLINTEGRATION T2.3 (USE-009): automatischer
                # Snapshot nach jedem Auto-Edit-Apply — Timeline ist damit
                # nach Crash/Fehlbedienung ueber die Snapshot-UI
                # wiederherstellbar. Fehler duerfen den Apply nie brechen.
                try:
                    from services.timeline_snapshot_service import create_snapshot
                    create_snapshot(
                        project_id, f"Auto-Edit {inserted} Segmente (auto)")
                except Exception as _snap_exc:
                    logger.warning(
                        "Auto-Snapshot nach Apply fehlgeschlagen: %s", _snap_exc)
                return inserted
            except OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    wait = 5 * (attempt + 1)
                    logger.warning("DB locked bei Timeline-Write, Retry %d/%d (warte %ds)...",
                                   attempt + 1, max_retries, wait)
                    _time.sleep(wait)
                else:
                    raise


def _do_apply_segments(segments: list[dict], project_id: int) -> int:
    """B-079: nutzt jetzt den kanonischen ``nullpool_session()`` Helper
    statt einer eigenen Engine-Konstruktion. Vorher fehlte hier
    ``PRAGMA foreign_keys=ON`` und der ``busy_timeout`` war auf 10s
    statt 120s. ``nullpool_session()`` liefert den korrekten Setup
    + auto-commit + auto-dispose und ist die Single-Source-of-Truth
    fuer NullPool-Writes (siehe D-020).

    SCHNITT-Redesign 2026-05-09 (Phase 06 / Task 6.2 — Risiko #3):
    Lock-aware. Gelockte Video-Eintraege werden NICHT geloescht;
    neue Segmente, die in eine Locked-Range hineinragen, werden auf
    deren Boundaries geklemmt oder verworfen, falls sie vollstaendig
    innerhalb liegen. Akzeptiert sowohl ``seg["media_id"]`` (neuer
    Plan-Style) als auch das Legacy-Feld ``seg["video_id"]``.
    """
    from database import nullpool_session

    inserted = 0
    with nullpool_session() as session:
        # 1) Locked-Ranges einsammeln (Boundaries der gesperrten Clips)
        locked_rows = (
            session.query(TimelineEntry)
            .filter_by(project_id=project_id, track="video", locked=True)
            .all()
        )
        locked_ranges: list[tuple[float, float]] = [
            (r.start_time, r.end_time)
            for r in locked_rows
            if r.start_time is not None and r.end_time is not None
        ]
        # T4.9: Locked-Ranges nach start_time sortieren. Bei mehreren Locks
        # iteriert die Klemm-Schleife sonst in DB-Insert-Reihenfolge — das
        # ist nicht deterministisch und macht das Klemmen unvorhersehbar,
        # wenn eine spaetere (zeitlich frueher liegende) Range das Segment
        # bereits beschnitten hat.
        locked_ranges.sort()

        # 2) Nur ungelockte Video-Eintraege loeschen — Locked bleibt unangetastet
        session.query(TimelineEntry).filter_by(
            project_id=project_id, track="video", locked=False
        ).delete()

        # 3) Neue Segmente einfuegen, an Locked-Ranges geklemmt.
        #
        # B-641 / T4.10 (D16): Ein Segment, das MEHRERE Locks ueberspannt
        # (z.B. seg=[0,30], locks=[(10,15),(20,25)]), wird pro Lock in
        # Stuecke gesplittet statt nur vor dem ersten ueberspannenden Lock
        # geklemmt zu werden — sonst gehen die Stuecke zwischen den Locks
        # und nach dem letzten Lock verloren. Interval-Subtraktion:
        # jede Locked-Range schneidet die aktuelle Stueckliste, sortiert
        # (T4.9) fuer deterministisches Ergebnis.
        for seg in segments:
            source_start0 = float(seg.get("source_start", 0.0) or 0.0)
            raw_source_end = seg.get("source_end")
            source_end0 = float(raw_source_end) if raw_source_end is not None else None

            # Stueck = (seg_start, seg_end, source_start, source_end)
            pieces = [(float(seg["start"]), float(seg["end"]), source_start0, source_end0)]
            for lr_start, lr_end in locked_ranges:
                if not pieces:
                    break
                next_pieces = []
                for p_start, p_end, p_src_start, p_src_end in pieces:
                    # Komplett ausserhalb -> kein Konflikt
                    if p_end <= lr_start or p_start >= lr_end:
                        next_pieces.append((p_start, p_end, p_src_start, p_src_end))
                        continue
                    # Komplett innerhalb der Locked-Range -> verwerfen
                    if p_start >= lr_start and p_end <= lr_end:
                        continue
                    # Linkes Reststueck vor der Locked-Range
                    if p_start < lr_start:
                        left_end = lr_start
                        delta = p_end - left_end
                        left_src_end = p_src_end
                        if p_src_end is not None and delta > 0.0:
                            left_src_end = round(max(p_src_start, p_src_end - delta), 4)
                        next_pieces.append((p_start, left_end, p_src_start, left_src_end))
                    # Rechtes Reststueck nach der Locked-Range
                    if p_end > lr_end:
                        right_start = lr_end
                        delta = right_start - p_start
                        right_src_start = round(p_src_start + delta, 4) if delta > 0.0 else p_src_start
                        next_pieces.append((right_start, p_end, right_src_start, p_src_end))
                pieces = next_pieces

            # Polymorphes Feld ``media_id``: Plan-Style ``seg["media_id"]``
            # ODER Legacy ``seg["video_id"]`` (Auto-Edit-Worker, undo_commands).
            mid = seg.get("media_id", seg.get("video_id"))
            if mid is None:
                raise KeyError(
                    "apply_auto_edit_segments: segment requires "
                    "'media_id' or 'video_id'"
                )

            for seg_start, seg_end, source_start, source_end in pieces:
                if source_end is not None:
                    source_span = source_end - source_start
                    if source_span <= 1e-3:
                        continue
                    if (seg_end - seg_start) > source_span:
                        seg_end = round(seg_start + source_span, 4)
                if (seg_end - seg_start) <= 1e-3:
                    continue

                entry = TimelineEntry(
                    project_id=project_id,
                    track="video",
                    media_id=mid,
                    start_time=seg_start,
                    end_time=seg_end,
                    source_start=source_start,
                    source_end=source_end,
                    lane=seg.get("lane", 0),
                    crossfade_duration=seg.get("crossfade_duration", seg.get("crossfade", 0.0)),
                    brightness=seg.get("brightness", 0.0),
                    contrast=seg.get("contrast", 1.0),
                    locked=False,
                )
                session.add(entry)
                inserted += 1
        # SCHNITT-Redesign 2026-05-09 (Phase 06 / Task 6.2): expliziter
        # commit damit der Lock-aware-Path auch in Test-Sessions
        # (in-memory + plain Session) persistiert. ``nullpool_session``
        # skipt den auto-commit dann (M5-FIX in database/session.py).
        session.commit()

    logger.info(
        "Timeline: %d Video-Segmente geschrieben (project=%d, locked-aware)",
        inserted, project_id,
    )
    return inserted


def repair_timeline_integrity(project_id: int) -> dict[str, int]:
    """Repariert bestehende SCHNITT-Timeline-Zeilen ohne Medien zu loeschen.

    B-319: Alte Auto-Edit-Laeufe konnten Timeline-Dauern schreiben, die laenger
    als ``source_end - source_start`` waren. Ausserdem konnte das manuelle
    Audio-Hinzufuegen denselben A1-Master mehrfach hintereinander eintragen.
    """
    from database import AudioTrack, VideoClip, nullpool_session

    result = {
        "video_duration_clamped": 0,
        "video_overlaps_shifted": 0,
        "video_gaps_closed": 0,
        "video_source_span_rebuilt": 0,
        "audio_duplicates_removed": 0,
        "audio_duration_synced": 0,
    }
    with nullpool_session() as session:
        video_rows = (
            session.query(TimelineEntry)
            .filter_by(project_id=project_id, track="video")
            .order_by(TimelineEntry.start_time, TimelineEntry.id)
            .all()
        )
        # E6 (Perf): Dauer-Lookup vorab als 2 Spalten-Queries statt
        # ``session.get(VideoClip/AudioTrack)`` pro Row. session.get
        # laedt das komplette ORM-Objekt inkl. aller Eager-Loads,
        # gebraucht wird hier aber nur ``duration``. Fehlende IDs sind
        # nicht im Dict — ``dict.get`` liefert dann None und verhaelt
        # sich exakt wie ``session.get -> None`` (bzw. wie
        # ``duration is None``, beides ergibt denselben Falsy-Pfad).
        video_media_ids = {
            row.media_id for row in video_rows if row.media_id is not None
        }
        video_durations: dict[int, float | None] = (
            dict(
                session.query(VideoClip.id, VideoClip.duration)
                .filter(VideoClip.id.in_(video_media_ids))
            )
            if video_media_ids
            else {}
        )
        cursor = 0.0
        for row in video_rows:
            start = float(row.start_time or 0.0)
            end = float(row.end_time or start)
            if row.source_start is not None and row.source_end is not None:
                source_span = float(row.source_end) - float(row.source_start)
                duration = end - start
                if source_span <= 1e-3 and duration > 1e-3:
                    # E6: Lookup statt session.get — fehlender Clip UND
                    # ``duration=None`` ergeben beide 0.0 (wie vorher).
                    clip_duration = (
                        float(video_durations.get(row.media_id) or 0.0)
                        if row.media_id is not None
                        else 0.0
                    )
                    source_start = float(row.source_start or 0.0)
                    available = clip_duration - source_start if clip_duration > source_start else duration
                    if available > 1e-3:
                        row.source_end = round(source_start + min(duration, available), 4)
                        source_span = float(row.source_end) - source_start
                        result["video_source_span_rebuilt"] += 1
                if source_span > 1e-3 and (end - start) > source_span + 1e-3:
                    end = round(start + source_span, 4)
                    row.end_time = end
                    result["video_duration_clamped"] += 1
            if start < cursor and not bool(row.locked):
                duration = max(0.0, end - start)
                start = round(cursor, 4)
                end = round(start + duration, 4)
                row.start_time = start
                row.end_time = end
                result["video_overlaps_shifted"] += 1
            elif start > cursor + 1e-3 and not bool(row.locked):
                duration = max(0.0, end - start)
                start = round(cursor, 4)
                end = round(start + duration, 4)
                row.start_time = start
                row.end_time = end
                result["video_gaps_closed"] += 1
            cursor = max(cursor, float(row.end_time or end))

        audio_rows = (
            session.query(TimelineEntry)
            .filter_by(project_id=project_id, track="audio")
            .order_by(TimelineEntry.start_time, TimelineEntry.id)
            .all()
        )
        # E6 (Perf): analog zum Video-Pfad — eine Spalten-Query statt
        # ``session.get(AudioTrack)`` pro Row. ``track and track.duration``
        # (Track fehlt ODER duration falsy -> skip) wird 1:1 durch den
        # Falsy-Check auf dem Dict-Lookup abgebildet.
        audio_media_ids = {
            row.media_id for row in audio_rows if row.media_id is not None
        }
        audio_durations: dict[int, float | None] = (
            dict(
                session.query(AudioTrack.id, AudioTrack.duration)
                .filter(AudioTrack.id.in_(audio_media_ids))
            )
            if audio_media_ids
            else {}
        )
        seen_audio: set[tuple[int | None, int]] = set()
        for row in audio_rows:
            key = (row.media_id, int(row.lane or 0))
            if key in seen_audio:
                session.delete(row)
                result["audio_duplicates_removed"] += 1
            else:
                seen_audio.add(key)
                track_duration = (
                    audio_durations.get(row.media_id)
                    if row.media_id is not None
                    else None
                )
                if track_duration:
                    expected_start = 0.0
                    expected_end = round(float(track_duration), 4)
                    current_start = float(row.start_time or 0.0)
                    current_end = float(row.end_time or current_start)
                    if (
                        abs(current_start - expected_start) > 1e-3
                        or abs(current_end - expected_end) > 1e-3
                    ):
                        row.start_time = expected_start
                        row.end_time = expected_end
                        row.source_start = 0.0
                        row.source_end = expected_end
                        result["audio_duration_synced"] += 1

        session.commit()

    logger.info("Timeline-Integritaet repariert (project=%d): %s", project_id, result)
    return result


def _safe_metadata_value(val: Any) -> Any:
    """Konvertiert OTIO AnyVector/AnyDictionary zurueck in native Python-Typen.

    PoC-Erkenntnis R2: Beim Deserialisieren werden Python-Listen zu
    opentimelineio._otio.AnyVector. Diese muessen vor dem Zugriff
    in list() konvertiert werden, sonst schlagen Index-Operationen fehl.
    """
    type_name = type(val).__name__
    # AnyDictionary muss VOR AnyVector geprueft werden (beide sind iterable)
    if type_name == "AnyDictionary" or isinstance(val, dict):
        return {k: _safe_metadata_value(v) for k, v in val.items()}
    if type_name == "AnyVector":
        return [_safe_metadata_value(v) for v in val]
    if hasattr(val, "__iter__") and not isinstance(val, (str, bytes)):
        try:
            return [_safe_metadata_value(v) for v in val]
        except TypeError:
            return val
    return val


def safe_get_metadata(metadata: dict, namespace: str = PB_NS) -> dict:
    """Liest pb_studio Metadata aus einem OTIO-Objekt und konvertiert AnyVector -> list.

    Verwendung:
        marker = timeline.tracks.markers[0]
        pb = safe_get_metadata(marker.metadata)
        audio_features = pb.get("audio_features")  # garantiert Python list
    """
    raw = metadata.get(namespace)
    if raw is None:
        return {}
    return _safe_metadata_value(raw)


class TimelineService:
    """Verwaltet OTIO-basierte Timelines fuer PB Studio."""

    def __init__(self, fps: float = 30.0):
        self.fps = fps
        self._timeline: otio.schema.Timeline | None = None
        # B-078: Lock fuer den Lazy-Init. Ohne den Lock konnten zwei
        # Threads gleichzeitig ``self._timeline = self.create_timeline(...)``
        # ausfuehren und sich gegenseitig ueberschreiben — Clip-Verlust war
        # die Folge. Double-checked locking im Getter unten.
        self._timeline_lock = threading.Lock()

    @property
    def timeline(self) -> otio.schema.Timeline:
        if self._timeline is None:
            with self._timeline_lock:
                if self._timeline is None:  # B-078: double-check inside lock
                    self._timeline = self.create_timeline("Untitled")
        return self._timeline

    @timeline.setter
    def timeline(self, tl: otio.schema.Timeline) -> None:
        self._timeline = tl

    def create_timeline(self, name: str) -> otio.schema.Timeline:
        """Erstellt eine neue OTIO-Timeline mit Video- und Audio-Track."""
        tl = otio.schema.Timeline(name=name)
        tl.tracks.append(
            otio.schema.Track(name="V1", kind=otio.schema.TrackKind.Video)
        )
        tl.tracks.append(
            otio.schema.Track(name="A1", kind=otio.schema.TrackKind.Audio)
        )
        self._timeline = tl
        return tl

    def get_video_track(self, index: int = 0) -> otio.schema.Track:
        """Gibt den Video-Track am Index zurueck (erstellt ihn ggf.)."""
        video_tracks = [
            t for t in self.timeline.tracks
            if t.kind == otio.schema.TrackKind.Video
        ]
        if index < len(video_tracks):
            return video_tracks[index]
        # Neuen Video-Track erstellen
        name = f"V{len(video_tracks) + 1}"
        track = otio.schema.Track(name=name, kind=otio.schema.TrackKind.Video)
        self.timeline.tracks.append(track)
        return track

    def get_audio_track(self, index: int = 0) -> otio.schema.Track:
        """Gibt den Audio-Track am Index zurueck (erstellt ihn ggf.)."""
        audio_tracks = [
            t for t in self.timeline.tracks
            if t.kind == otio.schema.TrackKind.Audio
        ]
        if index < len(audio_tracks):
            return audio_tracks[index]
        name = f"A{len(audio_tracks) + 1}"
        track = otio.schema.Track(name=name, kind=otio.schema.TrackKind.Audio)
        self.timeline.tracks.append(track)
        return track

    def add_clip(
        self,
        track: otio.schema.Track,
        name: str,
        media_path: str,
        source_start: float,
        source_duration: float,
        available_duration: float | None = None,
        metadata: dict | None = None,
    ) -> otio.schema.Clip:
        """Fuegt einen Clip zu einem Track hinzu.

        Args:
            track: Ziel-Track
            name: Clip-Name
            media_path: Pfad zur Mediendatei
            source_start: Start-Zeitpunkt in Sekunden im Quellmaterial
            source_duration: Dauer in Sekunden
            available_duration: Gesamtlaenge des Quellmaterials (optional)
            metadata: Zusaetzliche pb_studio Metadata
        """
        avail_dur = available_duration or source_duration
        ref = otio.schema.ExternalReference(
            target_url=media_path,
            available_range=TimeRange(
                start_time=RationalTime(0, self.fps),
                duration=RationalTime(avail_dur * self.fps, self.fps),
            ),
        )
        clip = otio.schema.Clip(
            name=name,
            media_reference=ref,
            source_range=TimeRange(
                start_time=RationalTime(source_start * self.fps, self.fps),
                duration=RationalTime(source_duration * self.fps, self.fps),
            ),
        )
        if metadata:
            clip.metadata[PB_NS] = metadata
        track.append(clip)
        return clip

    def add_transition(
        self,
        track: otio.schema.Track,
        position: int,
        duration: float,
        transition_type: str = "SMPTE_Dissolve",
    ) -> otio.schema.Transition:
        """Fuegt eine Transition (Crossfade) zwischen zwei Clips ein.

        Args:
            track: Ziel-Track
            position: Index in der Track-Children-Liste
            duration: Dauer in Sekunden
        """
        half = duration / 2.0
        t = otio.schema.Transition(
            name=f"Crossfade_{position}",
            transition_type=transition_type,
            in_offset=RationalTime(half * self.fps, self.fps),
            out_offset=RationalTime(half * self.fps, self.fps),
        )
        track.insert(position, t)
        return t

    def add_marker(
        self,
        name: str,
        time: float,
        duration: float = 0.0,
        color: str = "RED",
        metadata: dict | None = None,
    ) -> otio.schema.Marker:
        """Fuegt einen Marker (Anchor) zur Timeline hinzu.

        Args:
            name: Marker-Name
            time: Zeitpunkt in Sekunden
            duration: Dauer in Sekunden (0 = Punkt-Marker)
            color: Marker-Farbe (RED, GREEN, BLUE, etc.)
            metadata: pb_studio Metadata (audio_features, video_embedding, etc.)
        """
        color_enum = getattr(otio.schema.MarkerColor, color, otio.schema.MarkerColor.RED)
        marker = otio.schema.Marker(
            name=name,
            marked_range=TimeRange(
                start_time=RationalTime(time * self.fps, self.fps),
                duration=RationalTime(duration * self.fps, self.fps),
            ),
            color=color_enum,
            metadata={PB_NS: metadata or {}},
        )
        self.timeline.tracks.markers.append(marker)
        return marker

    def get_markers(self) -> list[dict]:
        """Gibt alle Timeline-Marker mit konvertierten Metadata zurueck."""
        result = []
        for m in self.timeline.tracks.markers:
            pb = safe_get_metadata(m.metadata)
            start_sec = m.marked_range.start_time.value / m.marked_range.start_time.rate
            dur_sec = m.marked_range.duration.value / m.marked_range.duration.rate
            result.append({
                "name": m.name,
                "time": start_sec,
                "duration": dur_sec,
                "color": str(m.color),
                "metadata": pb,
            })
        return result

    def get_all_clips(self) -> list[otio.schema.Clip]:
        """Gibt alle Clips in der Timeline zurueck."""
        return list(self.timeline.find_clips())

    def set_beatgrid_metadata(self, beat_positions: list[float], bpm: float) -> None:
        """Speichert das Beatgrid als Track-Metadata."""
        self.timeline.metadata[PB_NS] = {
            "bpm": bpm,
            "beat_positions": beat_positions,
        }

    def get_beatgrid_metadata(self) -> dict:
        """Liest das Beatgrid aus der Timeline-Metadata."""
        return safe_get_metadata(self.timeline.metadata)

    # --- Export ---

    def save_otio(self, path: str | Path) -> str:
        """Speichert die Timeline als OTIO-JSON."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        otio.adapters.write_to_file(self.timeline, str(path))
        return str(path)

    def load_otio(self, path: str | Path) -> otio.schema.Timeline:
        """Laedt eine Timeline aus einer OTIO-Datei."""
        tl = otio.adapters.read_from_file(str(path))
        self._timeline = tl
        return tl

    def export_edl(self, path: str | Path | None = None) -> str:
        """Exportiert die Timeline als CMX 3600 EDL (DaVinci Resolve kompatibel)."""
        exports_dir = _get_exports_dir()
        exports_dir.mkdir(parents=True, exist_ok=True)
        if path is None:
            path = exports_dir / f"{self.timeline.name}.edl"
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            otio.adapters.write_to_file(self.timeline, str(path), adapter_name="cmx_3600")
        except (ImportError, ValueError, RuntimeError, OSError, otio.exceptions.NotSupportedError):
            raise RuntimeError(
                "EDL-Export fehlgeschlagen — cmx_3600 Adapter nicht verfuegbar. "
                "Installiere: pip install otio-cmx3600-adapter"
            )
        return str(path)

    def get_duration(self) -> float:
        """Berechnet die Gesamtdauer der Timeline in Sekunden."""
        try:
            dur = self.timeline.duration()
            return dur.value / dur.rate
        except (ValueError, ZeroDivisionError, AttributeError) as e:
            logger.warning("Timeline-Dauer konnte nicht berechnet werden: %s", e)
            return 0.0

    def clear(self) -> None:
        """Leert die Timeline (entfernt alle Tracks und Marker)."""
        name = self.timeline.name if self._timeline else "Untitled"
        self.create_timeline(name)


def get_cut_list(project_id: int) -> list[dict]:
    """B-295: Liefert Cutliste eines Projekts als sortierte Liste von dicts.

    Format pro Eintrag:
        {"index": int, "time": float, "duration": float, "source": str,
         "strength": float, "locked": bool, "clip_id": int, "title": str}

    HINWEIS (I-1, 2026-05-11): TimelineEntry-Schema hat aktuell keine
    ``cut_source``/``cut_strength``-Felder — diese werden via getattr-Default
    auf ``""`` / ``0.0`` gesetzt. UI rendert die beiden Spalten aktuell NICHT
    (Source/Strength-Spalten entfernt aus CutListPanel bis Schema-Migration
    ``cut_source``/``cut_strength`` persistent macht). Forward-Compat
    bleibt im dict-Format erhalten, damit kuenftige Konsumenten die Keys
    weiterhin lesen koennen, sobald das Schema erweitert ist.

    Die Spalte ``track`` wird auf ``"video"`` gefiltert; sortiert wird nach
    ``start_time``.
    """
    from database import nullpool_session, TimelineEntry, VideoClip

    rows: list[dict] = []
    with nullpool_session() as s:
        entries = (
            s.query(
                TimelineEntry.id,
                TimelineEntry.media_id,
                TimelineEntry.start_time,
                TimelineEntry.end_time,
                TimelineEntry.locked,
            )
            .filter_by(project_id=project_id, track="video")
            .order_by(TimelineEntry.start_time)
            .all()
        )
        media_ids = sorted({int(e.media_id) for e in entries if e.media_id})
        clips_by_id = {}
        if media_ids:
            clips = (
                s.query(VideoClip.id, VideoClip.file_path)
                .filter(VideoClip.id.in_(media_ids))
                .all()
            )
            clips_by_id = {clip.id: clip.file_path for clip in clips}

        for idx, e in enumerate(entries):
            clip_path = clips_by_id.get(e.media_id)
            start_t = float(e.start_time or 0.0)
            end_t = float(e.end_time or 0.0)
            if clip_path:
                try:
                    from pathlib import Path as _P
                    title = _P(clip_path).stem if clip_path else f"Clip {e.media_id}"
                except Exception:
                    title = f"Clip {e.media_id}"
            else:
                title = f"Clip {e.media_id}"
            rows.append({
                "index": idx,
                "entry_id": int(e.id),  # B-295: TimelineEntry-ID fuer Lock/Remove
                "time": start_t,
                "duration": max(0.0, end_t - start_t),
                "source": str(getattr(e, "cut_source", "") or ""),
                "strength": float(getattr(e, "cut_strength", 0.0) or 0.0),
                "locked": bool(getattr(e, "locked", False)),
                "clip_id": e.media_id,
                "title": title or f"Clip {e.media_id}",
            })
    return rows
