"""B-875: Move/Undo/Redo muss selektierte Inspector-Payload erneuern."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from database.models import TimelineEntry


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_b875_sync_position_reemits_selected_clip_payload(
    db_session, project, video_clip, monkeypatch
) -> None:
    """Zentraler MoveCommand-Sync muss Inspector-Binder erneut anstossen."""
    app = _qapp()
    import database
    import ui.timeline as timeline_mod
    from ui.timeline import InteractiveTimeline, PIXELS_PER_SECOND

    monkeypatch.setattr(timeline_mod, "nullpool_session", database.nullpool_session)

    entry = TimelineEntry(
        project_id=project.id,
        track="video",
        media_id=video_clip.id,
        start_time=0.0,
        end_time=8.0,
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)

    timeline = InteractiveTimeline()
    try:
        timeline._brain_v3_timeline_meta = {}
        timeline._anchor_map = {}
        timeline._build_entries([entry], {}, {video_clip.id: video_clip}, {})
        timeline.materialize_all()

        item = timeline._find_clip_item(entry.id)
        assert item is not None
        item.setSelected(True)
        app.processEvents()

        payloads: list[list[dict]] = []
        timeline.selection_changed.connect(lambda data: payloads.append(data))

        timeline._sync_clip_position(entry.id, 4.14)
        app.processEvents()

        assert payloads, "Move/Undo/Redo-Sync emittiert selektierte Payload nicht erneut"
        moved = payloads[-1]
        assert len(moved) == 1
        assert moved[0]["entry_id"] == entry.id
        assert moved[0]["pos_x"] == 4.14 * PIXELS_PER_SECOND
    finally:
        try:
            timeline._cancel_pending_db_load()
        except Exception:
            pass
        timeline.deleteLater()
        app.processEvents()
