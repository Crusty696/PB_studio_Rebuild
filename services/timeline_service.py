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

from database import engine, get_active_project_id
from database import TimelineEntry
from sqlalchemy.orm import Session

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
                return _do_apply_segments(segments, project_id)
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

        # 3) Neue Segmente einfuegen, an Locked-Ranges geklemmt
        for seg in segments:
            seg_start = float(seg["start"])
            seg_end = float(seg["end"])
            skip = False
            for lr_start, lr_end in locked_ranges:
                # Komplett ausserhalb -> kein Konflikt
                if seg_end <= lr_start or seg_start >= lr_end:
                    continue
                # Komplett innerhalb der Locked-Range -> verwerfen
                if seg_start >= lr_start and seg_end <= lr_end:
                    skip = True
                    break
                # Linke Kante ragt in die Locked-Range -> rechts klemmen
                if seg_start < lr_start and seg_end > lr_start and seg_end <= lr_end:
                    seg_end = lr_start
                # Rechte Kante ragt aus der Locked-Range -> links klemmen
                elif seg_start >= lr_start and seg_start < lr_end and seg_end > lr_end:
                    seg_start = lr_end
                # Locked-Range ist komplett im Segment -> auf erste Haelfte
                # klemmen, hintere Haelfte geht verloren (selten; Plan-Verhalten)
                elif seg_start < lr_start and seg_end > lr_end:
                    seg_end = lr_start
            if skip or (seg_end - seg_start) <= 1e-3:
                continue

            # Polymorphes Feld ``media_id``: Plan-Style ``seg["media_id"]``
            # ODER Legacy ``seg["video_id"]`` (Auto-Edit-Worker, undo_commands).
            mid = seg.get("media_id", seg.get("video_id"))
            if mid is None:
                raise KeyError(
                    "apply_auto_edit_segments: segment requires "
                    "'media_id' or 'video_id'"
                )

            entry = TimelineEntry(
                project_id=project_id,
                track="video",
                media_id=mid,
                start_time=seg_start,
                end_time=seg_end,
                source_start=seg.get("source_start", 0.0),
                source_end=seg.get("source_end"),
                lane=seg.get("lane", 0),
                crossfade_duration=seg.get("crossfade_duration", 0.0),
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

    def export_otio_json(self, path: str | Path | None = None) -> str:
        """Exportiert die Timeline als OTIO-JSON."""
        exports_dir = _get_exports_dir()
        exports_dir.mkdir(parents=True, exist_ok=True)
        if path is None:
            path = exports_dir / f"{self.timeline.name}.otio"
        return self.save_otio(path)

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
