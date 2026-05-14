from __future__ import annotations

import os
from types import SimpleNamespace

from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_b320_video_timeline_clip_uses_thumbnail_pixmap(tmp_path):
    app = QApplication.instance() or QApplication([])
    assert app is not None

    thumb = QPixmap(96, 46)
    thumb.fill(QColor("#d4a44a"))
    thumb_path = tmp_path / "thumb.jpg"
    assert thumb.save(str(thumb_path))

    import ui.timeline as timeline_mod

    timeline = timeline_mod.InteractiveTimeline()
    timeline._brain_v3_timeline_meta = {}
    try:
        entry = SimpleNamespace(
            id=32001,
            media_id=11,
            track="video",
            start_time=0.0,
            end_time=5.0,
            locked=False,
        )
        video = SimpleNamespace(
            id=11,
            file_path="/tmp/source.mp4",
            duration=120.0,
        )

        timeline._build_entry_item(
            entry,
            audio_map={},
            video_map={11: video},
            anchor_map={},
            thumb_map={11: str(thumb_path)},
        )

        assert len(timeline.clip_items) == 1
        assert timeline.clip_items[0]._thumbnail_item is not None
        assert not timeline.clip_items[0]._thumbnail_item.pixmap().isNull()
    finally:
        timeline.deleteLater()
