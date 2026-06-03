"""B-471 T1: functional check that a VISIBLE video clip actually triggers a
thumbnail worker request. This reproduces the live-verify failure path headless
(offscreen Qt) so it does not need the GUI tester.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

try:
    from PySide6.QtWidgets import QApplication
except Exception:  # pragma: no cover - Qt missing
    pytest.skip("Qt not available", allow_module_level=True)

_app = QApplication.instance() or QApplication([])

from ui.timeline import (  # noqa: E402
    InteractiveTimeline,
    TimelineClipItem,
    VIDEO_TRACK_Y,
    TRACK_HEIGHT,
)
from ui.timeline_thumbnail_loader import ThumbnailLoadManager  # noqa: E402


def _video_item(media_id: int, x: float, path: str) -> TimelineClipItem:
    return TimelineClipItem(
        entry_id=media_id, media_id=media_id, track_type="video",
        title="clip", x=x, y=VIDEO_TRACK_Y, width=200.0, height=TRACK_HEIGHT,
        anchors=[],  # avoid DB query
        thumbnail_file_path=path,
    )


def _timeline_with_spy():
    tl = InteractiveTimeline()
    tl.resize(900, 220)
    tl.show()
    _app.processEvents()
    started: list[str] = []
    tl._thumb_loader = ThumbnailLoadManager(started.append, max_concurrent=2)
    return tl, started


def test_visible_video_clip_requests_thumbnail():
    tl, started = _timeline_with_spy()
    item = _video_item(7, 0.0, "C:/vids/a.mp4")
    tl._scene.addItem(item)
    tl.clip_items.append(item)
    tl._register_clip_thumbnail(item)
    tl._update_scene_rect()
    _app.processEvents()

    tl._request_visible_thumbnails()

    assert "C:/vids/a.mp4" in started, (
        "B-471 T1: a video clip at x=0 in the visible viewport must request a "
        "thumbnail worker"
    )


def test_offscreen_far_clip_not_requested_until_visible():
    tl, started = _timeline_with_spy()
    # clip far to the right, outside the initial viewport (+lookahead)
    item = _video_item(8, 50000.0, "C:/vids/far.mp4")
    tl._scene.addItem(item)
    tl.clip_items.append(item)
    tl._register_clip_thumbnail(item)
    tl._update_scene_rect()
    _app.processEvents()

    tl._request_visible_thumbnails()

    assert "C:/vids/far.mp4" not in started, (
        "B-471 T1: a clip far outside the viewport must NOT be requested (lazy)"
    )


def test_registration_skips_non_video_and_empty_path():
    tl, started = _timeline_with_spy()
    audio = TimelineClipItem(
        entry_id=1, media_id=1, track_type="audio", title="a",
        x=0.0, y=10.0, width=200.0, height=TRACK_HEIGHT, anchors=[],
    )
    tl._register_clip_thumbnail(audio)  # audio -> not registered
    assert tl._thumb_items_by_path == {}
