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


# ---------------------------------------------------------------------------
# T5.8 Coverage-Sweep (E8) — set_locked(False) Pen-Reset, Hit-Negativtest,
# Press-Geometry, Service+UI integration
# ---------------------------------------------------------------------------


def test_set_locked_false_resets_pen():
    """set_locked(False) → Pen wird auf _base_color.darker(120) zurueckgesetzt."""
    _qapp()
    clip = TimelineClipItem(
        entry_id=1, media_id=1, track_type="video", title="t",
        x=0, y=0, width=200, height=40,
        anchors=[],
    )
    expected = clip._base_color.darker(120)
    clip.set_locked(True)
    locked_pen = clip.pen().color().rgba()
    clip.set_locked(False)
    pen_after = clip.pen().color()
    assert pen_after.rgba() == expected.rgba()
    assert locked_pen != pen_after.rgba()


def test_hit_lock_icon_outside_returns_false():
    """Negativtest: Klick weit ausserhalb der Lock-Icon-BBox → False."""
    from PySide6.QtCore import QPointF
    _qapp()
    clip = TimelineClipItem(
        entry_id=1, media_id=1, track_type="video", title="t",
        x=0, y=0, width=200, height=40,
        anchors=[],
    )
    # Lock-Icon liegt rechtsbuendig oben — links unten ist garantiert ausserhalb
    assert clip._hit_lock_icon(QPointF(2.0, 35.0)) is False


def test_b320_video_clip_has_thumbnail_placeholder():
    _qapp()
    clip = TimelineClipItem(
        entry_id=1, media_id=42, track_type="video", title="clip42",
        x=0, y=0, width=200, height=40,
        anchors=[],
    )
    assert clip._thumbnail_item is not None
    assert not clip._thumbnail_item.pixmap().isNull()
    assert clip._thumbnail_item.zValue() < clip.lock_icon.zValue()


def test_b320_audio_clip_has_no_thumbnail_item():
    _qapp()
    clip = TimelineClipItem(
        entry_id=1, media_id=2, track_type="audio", title="audio",
        x=0, y=0, width=200, height=40,
        anchors=[],
    )
    assert clip._thumbnail_item is None
