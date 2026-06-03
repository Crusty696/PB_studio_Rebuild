"""B-471 T3: clip label must ignore the view transform so horizontal zoom does
not stretch/squash the text. Headless (offscreen Qt)."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

try:
    from PySide6.QtWidgets import QApplication, QGraphicsItem
except Exception:  # pragma: no cover
    pytest.skip("Qt not available", allow_module_level=True)

_app = QApplication.instance() or QApplication([])

from ui.timeline import TimelineClipItem, VIDEO_TRACK_Y, TRACK_HEIGHT  # noqa: E402


def _video_item():
    return TimelineClipItem(
        entry_id=1, media_id=1, track_type="video", title="my clip",
        x=0.0, y=VIDEO_TRACK_Y, width=200.0, height=TRACK_HEIGHT, anchors=[],
        thumbnail_file_path="C:/v/a.mp4",
    )


def test_label_ignores_view_transform():
    item = _video_item()
    flag = QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
    assert bool(item._label_item.flags() & flag), (
        "B-471 T3: clip label must set ItemIgnoresTransformations so zoom does "
        "not distort the text"
    )


def test_audio_clip_also_has_undistorted_label():
    item = TimelineClipItem(
        entry_id=2, media_id=2, track_type="audio", title="track",
        x=0.0, y=10.0, width=300.0, height=TRACK_HEIGHT, anchors=[],
    )
    flag = QGraphicsItem.GraphicsItemFlag.ItemIgnoresTransformations
    assert bool(item._label_item.flags() & flag)
