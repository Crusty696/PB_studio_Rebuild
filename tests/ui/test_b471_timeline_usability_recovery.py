from __future__ import annotations

from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QGraphicsTextItem

from ui.timeline import (
    AUDIO_TRACK_Y,
    TRACK_HEIGHT,
    VIDEO_TRACK_Y,
    InteractiveTimeline,
    TimelineClipItem,
)
from ui.timeline_thumbnail_loader import ThumbnailLoadManager
from ui.waveform_item import WaveformGraphicsItem
from ui.workspaces.schnitt.tab_pacing_anker import SchnittTabPacingAnker
from ui.workspaces.schnitt.timeline_shell import TimelineShell


def test_fit_to_content_keeps_vertical_scale_at_one(qapp) -> None:
    """B-471 recovery: Fit may compress time horizontally, not squash lanes vertically."""
    timeline = InteractiveTimeline()
    timeline.resize(900, 220)
    item = TimelineClipItem(
        entry_id=1,
        media_id=1,
        track_type="video",
        title="wide clip",
        x=0.0,
        y=VIDEO_TRACK_Y,
        width=12000.0,
        height=TRACK_HEIGHT,
        anchors=[],
        thumbnail_file_path="C:/videos/clip.mp4",
    )
    timeline.scene().addItem(item)
    timeline.clip_items.append(item)
    timeline._update_scene_rect()

    timeline.fit_to_content()

    assert timeline.transform().m22() == pytest.approx(1.0), (
        "Fit must not vertically scale A1/V1 lanes; user screenshot shows "
        "tracks squeezed upward and A1 nearly invisible."
    )


def test_video_thumbnail_item_covers_clip_width(qapp) -> None:
    """B-471 recovery: a long clip must not show a tiny 220px thumb then flat block."""
    item = TimelineClipItem(
        entry_id=2,
        media_id=2,
        track_type="video",
        title="long clip",
        x=0.0,
        y=VIDEO_TRACK_Y,
        width=800.0,
        height=TRACK_HEIGHT,
        anchors=[],
        thumbnail_file_path="C:/videos/long.mp4",
    )

    assert item._thumb_w >= int(item._clip_width), (
        "Timeline video thumbnail should cover the clip width so the user "
        "does not see a mostly empty gold rectangle."
    )


def test_visible_video_clip_requests_thumbnail_worker(qapp) -> None:
    """B-471 recovery: visible video clips with paths must request real thumbnails."""
    timeline = InteractiveTimeline()
    timeline.resize(900, 220)
    timeline.show()
    qapp.processEvents()
    requested: list[str] = []
    timeline._thumb_loader = ThumbnailLoadManager(requested.append, max_concurrent=2)
    item = TimelineClipItem(
        entry_id=20,
        media_id=20,
        track_type="video",
        title="visible clip",
        x=0.0,
        y=VIDEO_TRACK_Y,
        width=400.0,
        height=TRACK_HEIGHT,
        anchors=[],
        thumbnail_file_path="C:/videos/visible.mp4",
    )
    timeline.scene().addItem(item)
    timeline.clip_items.append(item)
    timeline._register_clip_thumbnail(item)
    timeline._update_scene_rect()
    qapp.processEvents()

    timeline._request_visible_thumbnails()

    assert "C:/videos/visible.mp4" in requested


def test_audio_clip_with_waveform_data_adds_waveform_item(qapp) -> None:
    """B-471 recovery: waveform data must become visible timeline waveform content."""
    timeline = InteractiveTimeline()
    waveform_data = SimpleNamespace(
        band_low="[0.1, 0.8, 0.2, 0.7]",
        band_mid="[0.2, 0.3, 0.4, 0.5]",
        band_high="[0.5, 0.4, 0.3, 0.2]",
        duration=4.0,
    )
    track = SimpleNamespace(
        waveform_data=waveform_data,
        beatgrid=SimpleNamespace(beat_positions="[0.0, 1.0, 2.0, 3.0]"),
    )
    entry = SimpleNamespace(start_time=1.0)

    timeline._load_waveform_for_track(
        session=None,
        track=track,
        entry=entry,
        dur=4.0,
        y=AUDIO_TRACK_Y,
    )

    assert any(isinstance(item, WaveformGraphicsItem) for item in timeline.waveform_items)
    assert any(isinstance(item, WaveformGraphicsItem) for item in timeline.scene().items())


def test_audio_clip_without_waveform_explains_missing_waveform(qapp) -> None:
    """B-471 recovery: a flat blue bar must explain that waveform data is missing."""
    item = TimelineClipItem(
        entry_id=3,
        media_id=3,
        track_type="audio",
        title="audio track",
        x=0.0,
        y=AUDIO_TRACK_Y,
        width=800.0,
        height=TRACK_HEIGHT,
        has_waveform=False,
        anchors=[],
    )

    text = "\n".join(
        child.toPlainText()
        for child in item.childItems()
        if isinstance(child, QGraphicsTextItem)
    )
    assert "Waveform fehlt" in text
    assert "Audioanalyse" in text


def test_pacing_tooltips_explain_effect_when_result(qapp) -> None:
    """B-471 recovery: pacing controls must explain effect, when to use, result."""
    tab = SchnittTabPacingAnker()
    controls = [
        tab.cut_rate_combo,
        tab.style_combo,
        tab.breakdown_combo,
        tab.reactivity_slider,
        tab.reactivity_spin,
        tab.vibe_input,
        tab.btn_regenerate,
        tab.anchor_list,
        tab.btn_add_anchor,
        tab.btn_remove_anchor,
        tab.btn_sync_anchors,
        tab.btn_learn_ai,
    ]

    for control in controls:
        tooltip = control.toolTip()
        assert "Wirkung:" in tooltip
        assert "Wann:" in tooltip
        assert "Ergebnis:" in tooltip


def test_timeline_toolbar_tooltips_explain_zoom_impact(qapp) -> None:
    shell = TimelineShell()
    controls = [
        shell.btn_zoom_out,
        shell.btn_zoom_fit,
        shell.btn_zoom_reset,
        shell.btn_zoom_in,
        shell.legend_label,
    ]

    for control in controls:
        tooltip = control.toolTip()
        assert "Wirkung:" in tooltip
        assert "Wann:" in tooltip
        assert "Ergebnis:" in tooltip
