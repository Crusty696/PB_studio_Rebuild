"""Undo/Redo Commands fuer Timeline-Operationen (QUndoCommand Pattern).

Jeder Command kapselt eine atomare Timeline-Operation und implementiert
undo() und redo() fuer bidirektionale Zustandsaenderungen in DB + UI.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from PySide6.QtCore import QTimer
from PySide6.QtGui import QUndoCommand

from database import nullpool_session, TimelineEntry

if TYPE_CHECKING:
    from ui.timeline import InteractiveTimeline

logger = logging.getLogger(__name__)


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
        with nullpool_session() as session:
            entry = session.get(TimelineEntry, self._entry_id)
            if entry:
                entry.start_time = round(start, 3)
                if end is not None:
                    entry.end_time = round(end, 3)
                session.commit()
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

    def redo(self):
        with nullpool_session() as session:
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
            session.commit()
            session.refresh(entry)
            self._entry_id = entry.id

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
        with nullpool_session() as session:
            entry = session.get(TimelineEntry, self._entry_id)
            if entry:
                session.delete(entry)
                session.commit()
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
        with nullpool_session() as session:
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
                session.commit()
        self._timeline._remove_clip_item(self._current_entry_id)

    def undo(self):
        if self._snapshot is None:
            return

        # Combine both DB operations in a single session to avoid orphaned rows
        from database import AudioTrack, VideoClip
        from pathlib import Path

        title = f"Clip #{self._snapshot['media_id']}"
        duration = 30.0 if self._snapshot["track"] == "audio" else 10.0

        with nullpool_session() as session:
            # M4-FIX: Gleiche ID wiederverwenden statt auto-increment,
            # damit andere Code-Teile die die alte ID gecacht haben weiterhin funktionieren.
            entry = TimelineEntry(id=self._current_entry_id, **self._snapshot)
            session.merge(entry)  # merge statt add: nutzt vorhandene ID

            # Look up title and duration in the same session
            if self._snapshot["track"] == "audio":
                obj = session.get(AudioTrack, self._snapshot["media_id"])
                if obj:
                    title = obj.title or title
                    duration = obj.duration or duration
            else:
                obj = session.get(VideoClip, self._snapshot["media_id"])
                if obj:
                    title = Path(obj.file_path).stem
                    duration = obj.duration or duration

            # Commit once after all DB operations complete
            session.commit()

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
        with nullpool_session() as session:
            entry = session.get(TimelineEntry, self._entry_id)
            if entry:
                entry.start_time = round(start, 3)
                if end is not None:
                    entry.end_time = round(end, 3)
                if source_start is not None:
                    entry.source_start = round(source_start, 3)
                if source_end is not None:
                    entry.source_end = round(source_end, 3)
                session.commit()
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
        old_entries_backup = []
        with nullpool_session() as session:
            old = (
                session.query(TimelineEntry)
                .filter_by(project_id=self._project_id, track="video")
                .all()
            )
            for e in old:
                old_entries_backup.append({
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

        from services.timeline_service import apply_auto_edit_segments
        apply_auto_edit_segments(self._new_segments, self._project_id)
        self._timeline.load_from_db(self._project_id)
        # Only save old_entries if redo succeeded
        self._old_entries = old_entries_backup

    def undo(self):
        if self._old_entries is None:
            return
        with nullpool_session() as session:
            session.query(TimelineEntry).filter_by(
                project_id=self._project_id, track="video"
            ).delete()
            for snap in self._old_entries:
                session.add(TimelineEntry(**snap))
            session.commit()
        self._timeline.load_from_db(self._project_id)
