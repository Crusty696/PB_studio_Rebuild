"""Undo/Redo Commands fuer Timeline-Operationen (QUndoCommand Pattern).

Jeder Command kapselt eine atomare Timeline-Operation und implementiert
undo() und redo() fuer bidirektionale Zustandsaenderungen in DB + UI.
"""

from __future__ import annotations

from contextlib import contextmanager
import logging
import time
from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer
from PySide6.QtGui import QUndoCommand

from database import TimelineEntry, engine, nullpool_session
from database import engine as _app_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session as DBSession

if TYPE_CHECKING:
    from ui.timeline import InteractiveTimeline

logger = logging.getLogger(__name__)

_DB_LOCK_RETRIES = 3
_DB_LOCK_RETRY_SLEEP_SEC = 0.25


def _is_database_locked(exc: OperationalError) -> bool:
    return "database is locked" in str(exc).lower()


@contextmanager
def _timeline_write_session():
    """Use NullPool for app writes, but keep monkeypatched test engines working."""
    if engine is _app_engine:
        with nullpool_session() as session:
            yield session
    else:
        with DBSession(engine) as session:
            yield session


def _run_timeline_write(operation, label: str):
    """Fuehrt DB-Schreiboperation aus. SQLite blockiert bei busy_timeout intern im C-Code.
    
    B-512: Kein time.sleep() im GUI-Thread mehr. Da PRAGMA busy_timeout=120s 
    aktiv ist, wartet SQLite selbstaendig bei Locks. Ein manueller Python-Sleep 
    ist unnoetig und blockiert die Benutzeroberflaeche. Wir versuchen den Write 
    dennoch transient _DB_LOCK_RETRIES Mal, ohne jedoch den Thread schlafen zu legen.
    """
    for attempt in range(1, _DB_LOCK_RETRIES + 1):
        try:
            with _timeline_write_session() as session:
                result = operation(session)
                session.commit()
                return result
        except OperationalError as exc:
            if not _is_database_locked(exc) or attempt >= _DB_LOCK_RETRIES:
                logger.exception("%s failed due to database operational error", label)
                raise
            logger.warning(
                "%s hit database lock; retrying immediately (%d/%d)",
                label,
                attempt + 1,
                _DB_LOCK_RETRIES,
            )
    raise RuntimeError(f"{label} failed without result")


class MoveClipCommand(QUndoCommand):
    """Verschiebt einen Clip auf der Timeline (Drag & Drop)."""

    def __init__(
        self,
        timeline: InteractiveTimeline,
        entry_id: int,
        old_start: float,
        old_end: float | None,
        new_start: float,
        new_end: float | None,
    ):
        super().__init__(f"Clip {entry_id} verschieben")
        self._timeline = timeline
        self._entry_id = entry_id
        self._old_start = old_start
        self._old_end = old_end
        self._new_start = new_start
        self._new_end = new_end

    def redo(self):
        self._apply(self._new_start, self._new_end)

    def undo(self):
        self._apply(self._old_start, self._old_end)

    def _apply(self, start: float, end: float | None):
        def _operation(session):
            entry = session.get(TimelineEntry, self._entry_id)
            if entry:
                entry.start_time = round(start, 3)
                if end is not None:
                    entry.end_time = round(end, 3)

        _run_timeline_write(_operation, "MoveClipCommand._apply")
        # FIX C-7: Queue UI update to main thread to avoid Qt threading violation
        QTimer.singleShot(0, lambda: self._timeline._sync_clip_position(self._entry_id, start))

    def id(self) -> int:
        """Merge-ID: Aufeinanderfolgende Moves desselben Clips verschmelzen."""
        return self._entry_id

    def mergeWith(self, other: QUndoCommand) -> bool:
        if not isinstance(other, MoveClipCommand):
            return False
        if other._entry_id != self._entry_id:
            return False
        self._new_start = other._new_start
        self._new_end = other._new_end
        return True


class AddClipCommand(QUndoCommand):
    """Fuegt einen Clip zur Timeline hinzu."""

    def __init__(
        self,
        timeline: InteractiveTimeline,
        project_id: int,
        track_type: str,
        media_id: int,
        title: str,
        start_time: float,
        duration: float,
        end_time: float | None = None,
        source_start: float = 0.0,
        source_end: float | None = None,
    ):
        super().__init__(f"{track_type.title()}-Clip hinzufuegen")
        self._timeline = timeline
        self._project_id = project_id
        self._track_type = track_type
        self._media_id = media_id
        self._title = title
        self._start_time = start_time
        self._duration = duration
        self._end_time = end_time if end_time is not None else round(start_time + duration, 3)
        self._source_start = source_start
        self._source_end = source_end
        self._entry_id: int | None = None
        self._replaced_entries: list[dict] = []

    def redo(self):
        def _operation(session):
            replaced_entries = []
            if self._track_type == "audio":
                existing_audio = (
                    session.query(TimelineEntry)
                    .filter_by(project_id=self._project_id, track="audio")
                    .all()
                )
                for old in existing_audio:
                    replaced_entries.append({
                        "project_id": old.project_id,
                        "track": old.track,
                        "media_id": old.media_id,
                        "start_time": old.start_time,
                        "end_time": old.end_time,
                        "lane": old.lane,
                        "source_start": old.source_start,
                        "source_end": old.source_end,
                        "crossfade_duration": old.crossfade_duration,
                        "brightness": old.brightness,
                        "contrast": old.contrast,
                        "locked": old.locked,
                    })
                    session.delete(old)

            entry = TimelineEntry(
                project_id=self._project_id,
                track=self._track_type,
                media_id=self._media_id,
                start_time=round(self._start_time, 3),
                end_time=round(self._end_time, 3),
                source_start=self._source_start,
                source_end=self._source_end,
                lane=0,
            )
            session.add(entry)
            session.flush()
            return int(entry.id), replaced_entries

        self._entry_id, self._replaced_entries = _run_timeline_write(
            _operation,
            "AddClipCommand.redo",
        )

        self._timeline.add_clip(
            entry_id=self._entry_id,
            media_id=self._media_id,
            track_type=self._track_type,
            title=self._title,
            start_time=self._start_time,
            duration=self._duration,
        )

    def undo(self):
        if self._entry_id is None:
            return

        def _operation(session):
            entry = session.get(TimelineEntry, self._entry_id)
            if entry:
                session.delete(entry)
            for snap in self._replaced_entries:
                session.add(TimelineEntry(**snap))

        _run_timeline_write(_operation, "AddClipCommand.undo")
        if self._track_type == "audio" and hasattr(self._timeline, "load_from_db"):
            self._timeline.load_from_db(self._project_id)
        else:
            self._timeline._remove_clip_item(self._entry_id)

    @property
    def entry_id(self) -> int | None:
        return self._entry_id


class RemoveClipCommand(QUndoCommand):
    """Entfernt einen Clip von der Timeline."""

    def __init__(
        self,
        timeline: InteractiveTimeline,
        entry_id: int,
    ):
        super().__init__(f"Clip {entry_id} entfernen")
        self._timeline = timeline
        self._original_entry_id = entry_id  # M-55 Fix: Store original ID separately
        self._current_entry_id = entry_id   # ID that changes with undo/redo cycles
        # Snapshot fuer Undo
        self._snapshot: dict | None = None

    def redo(self):
        # Snapshot vor dem Loeschen speichern
        def _operation(session):
            entry = session.get(TimelineEntry, self._current_entry_id)
            if entry:
                self._snapshot = {
                    "project_id": entry.project_id,
                    "track": entry.track,
                    "media_id": entry.media_id,
                    "start_time": entry.start_time,
                    "end_time": entry.end_time,
                    "lane": entry.lane,
                    "source_start": entry.source_start,
                    "source_end": entry.source_end,
                    "crossfade_duration": entry.crossfade_duration,
                    "brightness": entry.brightness,
                    "contrast": entry.contrast,
                }
                session.delete(entry)

        _run_timeline_write(_operation, "RemoveClipCommand.redo")
        self._timeline._remove_clip_item(self._current_entry_id)

    def undo(self):
        if self._snapshot is None:
            return

        # Combine both DB operations in a single session to avoid orphaned rows
        from database import AudioTrack, VideoClip
        from pathlib import Path
        from sqlalchemy import select

        def _operation(session):
            title = f"Clip #{self._snapshot['media_id']}"
            duration = 30.0 if self._snapshot["track"] == "audio" else 10.0

            # M4-FIX: Gleiche ID wiederverwenden statt auto-increment,
            # damit andere Code-Teile die die alte ID gecacht haben weiterhin funktionieren.
            entry = TimelineEntry(id=self._current_entry_id, **self._snapshot)
            session.merge(entry)  # merge statt add: nutzt vorhandene ID

            # Look up title and duration in the same session
            if self._snapshot["track"] == "audio":
                # B-625: column-select statt session.get — vermeidet den eager-join
                # von AudioTrack.beatgrid/waveform_data (lazy='joined' Blob-Spalten),
                # der den Qt-Main-Thread einfriert. Nur genutzte Skalarfelder laden.
                row = session.execute(
                    select(AudioTrack.title, AudioTrack.duration).where(
                        AudioTrack.id == self._snapshot["media_id"]
                    )
                ).first()
                if row:
                    title = row.title or title
                    duration = row.duration or duration
            else:
                obj = session.get(VideoClip, self._snapshot["media_id"])
                if obj:
                    title = Path(obj.file_path).stem
                    duration = obj.duration or duration

            # Commit uebernimmt _run_timeline_write nach Abschluss der Operation
            return title, duration

        title, duration = _run_timeline_write(_operation, "RemoveClipCommand.undo")

        self._timeline.add_clip(
            entry_id=self._current_entry_id,
            media_id=self._snapshot["media_id"],
            track_type=self._snapshot["track"],
            title=title,
            start_time=self._snapshot["start_time"],
            duration=duration,
        )


class TrimClipCommand(QUndoCommand):
    """Trimmt einen Clip (In/Out Point verschieben)."""

    def __init__(
        self,
        timeline: InteractiveTimeline,
        entry_id: int,
        old_start: float,
        old_end: float | None,
        old_source_start: float | None,
        old_source_end: float | None,
        new_start: float,
        new_end: float | None,
        new_source_start: float | None,
        new_source_end: float | None,
    ):
        super().__init__(f"Clip {entry_id} trimmen")
        self._timeline = timeline
        self._entry_id = entry_id
        self._old_start = old_start
        self._old_end = old_end
        self._old_source_start = old_source_start
        self._old_source_end = old_source_end
        self._new_start = new_start
        self._new_end = new_end
        self._new_source_start = new_source_start
        self._new_source_end = new_source_end

    def redo(self):
        self._apply(self._new_start, self._new_end,
                     self._new_source_start, self._new_source_end)

    def undo(self):
        self._apply(self._old_start, self._old_end,
                     self._old_source_start, self._old_source_end)

    def _apply(self, start: float, end: float | None,
               source_start: float | None, source_end: float | None):
        def _operation(session):
            entry = session.get(TimelineEntry, self._entry_id)
            if entry:
                entry.start_time = round(start, 3)
                if end is not None:
                    entry.end_time = round(end, 3)
                if source_start is not None:
                    entry.source_start = round(source_start, 3)
                if source_end is not None:
                    entry.source_end = round(source_end, 3)

        _run_timeline_write(_operation, "TrimClipCommand._apply")
        self._timeline._sync_clip_after_trim(self._entry_id, start, end)


class ApplyAutoEditCommand(QUndoCommand):
    """Ersetzt alle Video-Segmente auf der Timeline (Auto-Edit Batch-Operation)."""

    def __init__(
        self,
        timeline: InteractiveTimeline,
        project_id: int,
        new_segments: list[dict],
    ):
        super().__init__(f"Auto-Edit ({len(new_segments)} Segmente)")
        self._timeline = timeline
        self._project_id = project_id
        self._new_segments = new_segments
        self._old_entries: list[dict] | None = None

    def redo(self):
        # Alte Video-Entries sichern
        def _backup_operation(session):
            backup = []
            old = (
                session.query(TimelineEntry)
                .filter_by(project_id=self._project_id, track="video")
                .all()
            )
            for e in old:
                backup.append({
                    "project_id": e.project_id,
                    "track": e.track,
                    "media_id": e.media_id,
                    "start_time": e.start_time,
                    "end_time": e.end_time,
                    "lane": e.lane,
                    "source_start": e.source_start,
                    "source_end": e.source_end,
                    "crossfade_duration": e.crossfade_duration,
                    "brightness": e.brightness,
                    "contrast": e.contrast,
                })
            return backup

        old_entries_backup = _run_timeline_write(
            _backup_operation,
            "ApplyAutoEditCommand.redo.backup",
        )

        from services.timeline_service import apply_auto_edit_segments
        apply_started_at = time.perf_counter()
        apply_auto_edit_segments(self._new_segments, self._project_id)
        logger.info(
            "B-598 ApplyAutoEditCommand.redo apply_auto_edit_segments project_id=%s segments=%d duration_ms=%.1f",
            self._project_id,
            len(self._new_segments),
            (time.perf_counter() - apply_started_at) * 1000.0,
        )
        reload_started_at = time.perf_counter()
        self._timeline.load_from_db(self._project_id)
        logger.info(
            "B-598 ApplyAutoEditCommand.redo load_from_db project_id=%s duration_ms=%.1f",
            self._project_id,
            (time.perf_counter() - reload_started_at) * 1000.0,
        )
        # Only save old_entries if redo succeeded
        self._old_entries = old_entries_backup

    def undo(self):
        if self._old_entries is None:
            return

        def _operation(session):
            session.query(TimelineEntry).filter_by(
                project_id=self._project_id, track="video"
            ).delete()
            for snap in self._old_entries:
                session.add(TimelineEntry(**snap))

        _run_timeline_write(_operation, "ApplyAutoEditCommand.undo")
        self._timeline.load_from_db(self._project_id)


class ToggleClipLockCommand(QUndoCommand):
    """Togglet das locked-Flag eines TimelineEntry.

    SCHNITT-Redesign 2026-05-09 Phase 03 Task 3.3.
    Tier-1 Hardening (D11): Optionaler ``timeline``-Parameter — wenn
    gesetzt, ruft redo()/undo() nach dem DB-Write
    ``timeline._sync_clip_lock_visual(entry_id, locked)`` auf, damit
    Goldrand + Lock-Icon ohne Full-Reload mitziehen.
    """

    # T4.7 (D13): mergeWith-Fenster fuer aufeinanderfolgende Toggles desselben
    # Clips. 500ms ist tolerant fuer Doppel-Klicks/Tastatur-Spam ohne mit
    # bewussten getrennten Aktionen zu verschmelzen.
    _MERGE_WINDOW_S: float = 0.5

    def __init__(self, entry_id: int, new_locked: bool, timeline=None):
        super().__init__("Clip sperren" if new_locked else "Clip entsperren")
        self._entry_id = entry_id
        self._new = new_locked
        self._old: bool | None = None
        self._timeline = timeline
        self._created_at = time.monotonic()  # T4.7

    # T4.7: stabile Merge-ID — alle Toggles desselben Clips sind merge-faehig.
    def id(self) -> int:
        return self._entry_id ^ 0xC10C  # disjunkter Namespace zu MoveClipCommand

    def mergeWith(self, other: QUndoCommand) -> bool:
        """T4.7 (D13): Mergt zwei Toggles desselben Clips, wenn der spaetere
        innerhalb von _MERGE_WINDOW_S nach diesem erstellt wurde.

        Effekt:
        - Toggle A->B->A in <500ms ergibt eine Sequenz mit gleichem _old wie
          self._old (A) und _new = other._new (A) → No-op-Konsolidierung.
        - Visual-Sync wird durch other.redo() bereits gemacht; Merge selbst
          aendert nichts am DB-Zustand.
        """
        if not isinstance(other, ToggleClipLockCommand):
            return False
        if other._entry_id != self._entry_id:
            return False
        if (other._created_at - self._created_at) > self._MERGE_WINDOW_S:
            return False
        # other._new ueberschreibt; self._old bleibt (Original-Zustand).
        self._new = other._new
        return True

    def _sync_visual(self, locked: bool) -> None:
        if self._timeline is None:
            return
        sync = getattr(self._timeline, "_sync_clip_lock_visual", None)
        if callable(sync):
            try:
                sync(self._entry_id, locked)
            except Exception:
                logger.debug("ToggleClipLockCommand: visual sync skipped", exc_info=True)

    def redo(self):
        def _operation(s):
            e = s.get(TimelineEntry, self._entry_id)
            if e is None:
                return False
            self._old = bool(e.locked)
            e.locked = self._new
            return True

        if not _run_timeline_write(_operation, "ToggleClipLockCommand.redo"):
            return
        self._sync_visual(self._new)

    def undo(self):
        if self._old is None:
            return

        def _operation(s):
            e = s.get(TimelineEntry, self._entry_id)
            if e is None:
                return False
            e.locked = self._old
            return True

        if not _run_timeline_write(_operation, "ToggleClipLockCommand.undo"):
            return
        self._sync_visual(self._old)
