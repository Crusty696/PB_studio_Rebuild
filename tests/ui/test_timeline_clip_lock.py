"""TimelineClipItem locked state + visual (Phase 05 / Task 5.2)."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from ui.timeline import TimelineClipItem


def _qapp():
    return QApplication.instance() or QApplication([])


def test_clip_has_lock_icon():
    _qapp()
    clip = TimelineClipItem(
        entry_id=1, media_id=1, track_type="video", title="t",
        x=0, y=0, width=200, height=40,
        anchors=[],
    )
    assert clip.lock_icon is not None
    assert clip.is_locked() is False


def test_set_locked_updates_visual_and_state():
    _qapp()
    clip = TimelineClipItem(
        entry_id=1, media_id=1, track_type="video", title="t",
        x=0, y=0, width=200, height=40,
        anchors=[],
    )
    clip.set_locked(True)
    assert clip.is_locked() is True
    assert clip.lock_icon.is_locked is True
