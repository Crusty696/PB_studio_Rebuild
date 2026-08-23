"""B-876: Cutliste muss zentralen Move/Undo/Redo-Positionssync spiegeln."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from database.models import TimelineEntry


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_b876_position_sync_updates_only_matching_cutlist_time(
    db_session, project, video_clip, monkeypatch
) -> None:
    app = _qapp()
    import database
    import ui.timeline as timeline_mod
    from ui.workspaces.schnitt.tab_schnitt import SchnittTabSchnitt

    monkeypatch.setattr(timeline_mod, "nullpool_session", database.nullpool_session)

    entry = TimelineEntry(
        project_id=project.id,
        track="video",
        media_id=video_clip.id,
        start_time=4.14,
        end_time=12.14,
    )
    db_session.add(entry)
    db_session.commit()
    db_session.refresh(entry)

    tab = SchnittTabSchnitt()
    timeline = tab.timeline_view
    panel = tab.cut_list_panel
    try:
        timeline._brain_v3_timeline_meta = {}
        timeline._anchor_map = {}
        timeline._build_entries([entry], {}, {video_clip.id: video_clip}, {})
        timeline.materialize_all()
        panel._render_cuts(
            [
                {
                    "index": 0,
                    "entry_id": entry.id,
                    "time": 4.14,
                    "duration": 8.0,
                    "locked": False,
                    "title": "fixture",
                },
                {
                    "index": 1,
                    "entry_id": entry.id + 1000,
                    "time": 20.0,
                    "duration": 2.0,
                    "locked": False,
                    "title": "unrelated",
                },
            ]
        )

        timeline._sync_clip_position(entry.id, 8.24)
        app.processEvents()

        moved_time = panel.table.item(0, 1)
        unrelated_time = panel.table.item(1, 1)
        assert moved_time.text() == "8.24s"
        assert moved_time.data(Qt.ItemDataRole.UserRole) == 8.24
        assert unrelated_time.text() == "20.00s"
        assert unrelated_time.data(Qt.ItemDataRole.UserRole) == 20.0
    finally:
        timeline._move_timer.stop()
        timeline._pending_moves.clear()
        try:
            timeline._cancel_pending_db_load()
        except Exception:
            pass
        tab.deleteLater()
        app.processEvents()
