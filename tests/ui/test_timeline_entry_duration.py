from __future__ import annotations

import os
from types import SimpleNamespace

from PySide6.QtWidgets import QApplication

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_b318_video_clip_width_uses_timeline_entry_duration():
    app = QApplication.instance() or QApplication([])
    assert app is not None

    import ui.timeline as timeline_mod

    timeline = timeline_mod.InteractiveTimeline()
    timeline._brain_v3_timeline_meta = {}
    try:
        entry = SimpleNamespace(
            id=31801,
            media_id=7,
            track="video",
            start_time=10.0,
            end_time=15.25,
            locked=False,
        )
        video = SimpleNamespace(
            id=7,
            file_path="/tmp/very_long_source_clip.mp4",
            duration=120.0,
        )

        clip_end = timeline._build_entry_item(
            entry,
            audio_map={},
            video_map={7: video},
            anchor_map={},
        )
        # M1 Timeline-Virtualisierung (D-066): Video-Build erzeugt nur einen
        # Record; Item entsteht viewport-getrieben -> hier explizit.
        timeline.materialize_all()

        assert len(timeline.clip_items) == 1
        assert timeline.clip_items[0]._clip_width == 5.25 * timeline_mod.PIXELS_PER_SECOND
        assert clip_end == 15.25
    finally:
        timeline.deleteLater()


def test_b318_audio_clip_width_uses_timeline_entry_duration_without_waveform():
    app = QApplication.instance() or QApplication([])
    assert app is not None

    import ui.timeline as timeline_mod

    timeline = timeline_mod.InteractiveTimeline()
    timeline._brain_v3_timeline_meta = {}
    try:
        entry = SimpleNamespace(
            id=31802,
            media_id=2,
            track="audio",
            start_time=2.0,
            end_time=8.0,
            locked=False,
        )
        audio = SimpleNamespace(
            id=2,
            title="long master",
            duration=5531.005,
            waveform_data=None,
            beatgrid=None,
        )

        clip_end = timeline._build_entry_item(
            entry,
            audio_map={2: audio},
            video_map={},
            anchor_map={},
        )

        assert len(timeline.clip_items) == 1
        assert timeline.clip_items[0]._clip_width == 6.0 * timeline_mod.PIXELS_PER_SECOND
        assert clip_end == 8.0
    finally:
        timeline.deleteLater()
