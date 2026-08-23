"""B-877: Trim muss Auswahl, Inspector-Payload und Cutliste synchron halten."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, Qt
from PySide6.QtWidgets import QApplication

from database.models import TimelineEntry
from ui.timeline import PIXELS_PER_SECOND, TimelineClipItem


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


class _TrimPress:
    def __init__(self, local_x: float, scene_x: float):
        self._local = QPointF(local_x, 20.0)
        self._scene = QPointF(scene_x, 20.0)
        self.accepted = False

    def button(self):
        return Qt.MouseButton.LeftButton

    def pos(self):
        return self._local

    def scenePos(self):
        return self._scene

    def accept(self):
        self.accepted = True


def test_w5_trim_edge_press_selects_clip() -> None:
    _qapp()
    item = TimelineClipItem(
        entry_id=1,
        media_id=2,
        track_type="video",
        title="fixture",
        x=100.0,
        y=50.0,
        width=400.0,
        height=80.0,
    )
    event = _TrimPress(local_x=399.0, scene_x=499.0)

    item.mousePressEvent(event)

    assert event.accepted is True
    assert item._trim_mode == "right"
    assert item.isSelected() is True


def test_w5_trim_sync_reemits_inspector_payload_and_updates_cutlist(
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
        start_time=12.32,
        end_time=20.32,
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
        item = timeline._find_clip_item(entry.id)
        assert item is not None
        item.setSelected(True)
        app.processEvents()

        panel._render_cuts(
            [
                {
                    "index": 0,
                    "entry_id": entry.id,
                    "time": 12.32,
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
        payloads: list[list[dict]] = []
        timeline.selection_changed.connect(lambda data: payloads.append(data))

        timeline._sync_clip_after_trim(entry.id, 12.32, 18.32)
        app.processEvents()

        assert payloads, "Trim/Undo/Redo-Sync emittiert Inspector-Payload nicht erneut"
        trimmed = payloads[-1]
        assert len(trimmed) == 1
        assert trimmed[0]["entry_id"] == entry.id
        assert trimmed[0]["pos_x"] == 12.32 * PIXELS_PER_SECOND
        assert trimmed[0]["width"] == 6.0 * PIXELS_PER_SECOND
        assert panel.table.item(0, 1).text() == "12.32s"
        assert panel.table.item(0, 2).text() == "6.00s"
        assert panel.table.item(1, 1).text() == "20.00s"
        assert panel.table.item(1, 2).text() == "2.00s"

        payloads.clear()
        timeline._sync_clip_after_trim(entry.id, 13.32, 18.32)
        app.processEvents()

        assert payloads[-1][0]["pos_x"] == 13.32 * PIXELS_PER_SECOND
        assert payloads[-1][0]["width"] == 5.0 * PIXELS_PER_SECOND
        assert panel.table.item(0, 1).text() == "13.32s"
        assert panel.table.item(0, 2).text() == "5.00s"
        assert panel.table.item(1, 1).text() == "20.00s"
        assert panel.table.item(1, 2).text() == "2.00s"
    finally:
        timeline._move_timer.stop()
        timeline._pending_moves.clear()
        try:
            timeline._cancel_pending_db_load()
        except Exception:
            pass
        tab.deleteLater()
        app.processEvents()
