from __future__ import annotations

import json
import time
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QGraphicsItem, QGraphicsTextItem
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import ui.timeline as timeline_mod
from database import AudioTrack, Base, Beatgrid, Project, TimelineEntry, VideoClip, WaveformData
from ui.timeline import (
    AUDIO_TRACK_Y,
    MIN_READABLE_FIT_SCALE,
    TRACK_HEIGHT,
    VIDEO_TRACK_Y,
    InteractiveTimeline,
    TimelineClipItem,
)
from ui.timeline_thumbnail_loader import ThumbnailLoadManager
from ui.waveform_item import WaveformGraphicsItem
from ui.workspaces.schnitt.tab_schnitt import SchnittTabSchnitt
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


def test_fit_to_content_keeps_readable_thumbnail_scale(qapp) -> None:
    """B-471 live: full-project fit must not compress thumbnails into stripes."""
    timeline = InteractiveTimeline()
    timeline.resize(1200, 320)
    item = TimelineClipItem(
        entry_id=101,
        media_id=101,
        track_type="video",
        title="long project",
        x=0.0,
        y=VIDEO_TRACK_Y,
        width=75000.0,
        height=TRACK_HEIGHT,
        anchors=[],
        thumbnail_file_path="C:/videos/clip.mp4",
    )
    timeline.scene().addItem(item)
    timeline.clip_items.append(item)
    timeline._update_scene_rect()

    timeline.fit_to_content()

    assert timeline.transform().m11() >= MIN_READABLE_FIT_SCALE
    assert timeline.transform().m22() == pytest.approx(1.0)


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


def test_video_clip_explains_thumbnail_loading_or_missing_path(qapp) -> None:
    with_path = TimelineClipItem(
        entry_id=12,
        media_id=12,
        track_type="video",
        title="clip with path",
        x=0.0,
        y=VIDEO_TRACK_Y,
        width=800.0,
        height=TRACK_HEIGHT,
        anchors=[],
        thumbnail_file_path="C:/videos/clip.mp4",
    )
    no_path = TimelineClipItem(
        entry_id=13,
        media_id=13,
        track_type="video",
        title="clip without path",
        x=0.0,
        y=VIDEO_TRACK_Y,
        width=800.0,
        height=TRACK_HEIGHT,
        anchors=[],
        thumbnail_file_path=None,
    )

    with_path_text = "\n".join(
        child.toPlainText()
        for child in with_path.childItems()
        if isinstance(child, QGraphicsTextItem)
    )
    no_path_text = "\n".join(
        child.toPlainText()
        for child in no_path.childItems()
        if isinstance(child, QGraphicsTextItem)
    )

    assert "Thumbnail laedt" in with_path_text
    assert "Thumbnail fehlt" in no_path_text


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


def test_build_entry_item_adds_waveform_immediately_from_loaded_audio_map(qapp) -> None:
    """B-471 live: build completion must not depend on a late async waveform worker."""
    timeline = InteractiveTimeline()
    waveform_data = SimpleNamespace(
        band_low="[0.1, 0.8, 0.2, 0.7]",
        band_mid="[0.2, 0.3, 0.4, 0.5]",
        band_high="[0.5, 0.4, 0.3, 0.2]",
        duration=4.0,
    )
    audio = SimpleNamespace(
        id=41,
        title="loaded audio",
        duration=4.0,
        waveform_data=waveform_data,
        beatgrid=SimpleNamespace(beat_positions="[0.0, 1.0, 2.0, 3.0]"),
    )
    entry = SimpleNamespace(
        id=410,
        media_id=41,
        track="audio",
        start_time=0.0,
        end_time=4.0,
        locked=False,
    )

    timeline._build_entry_item(entry, audio_map={41: audio}, video_map={}, anchor_map={})

    assert len(timeline.clip_items) == 1
    assert any(isinstance(item, WaveformGraphicsItem) for item in timeline.waveform_items)


def test_load_from_db_preserves_media_maps_across_worker_signal(
    qapp,
    monkeypatch,
    tmp_path,
) -> None:
    """B-471 live: typed Qt dict signals dropped SQLAlchemy media maps."""
    test_engine = create_engine(
        f"sqlite:///{tmp_path / 'b471_worker.db'}",
        echo=False,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(test_engine)

    @contextmanager
    def _test_nullpool():
        with Session(test_engine) as session:
            yield session

    monkeypatch.setattr(timeline_mod, "nullpool_session", _test_nullpool)
    with Session(test_engine) as session:
        project = Project(
            name="b471-worker",
            path=str(tmp_path),
            resolution="1920x1080",
            fps=30.0,
        )
        session.add(project)
        session.flush()
        audio = AudioTrack(
            project_id=project.id,
            file_path="/tmp/audio.mp3",
            title="loaded audio",
            duration=8.0,
        )
        video = VideoClip(
            project_id=project.id,
            file_path="/tmp/video.mp4",
            duration=4.0,
            width=1920,
            height=1080,
            fps=30.0,
        )
        session.add_all([audio, video])
        session.flush()
        session.add_all(
            [
                WaveformData(
                    audio_track_id=audio.id,
                    num_samples=4,
                    duration=8.0,
                    band_low=[0.1, 0.8, 0.2, 0.7],
                    band_mid=[0.2, 0.3, 0.4, 0.5],
                    band_high=[0.5, 0.4, 0.3, 0.2],
                ),
                Beatgrid(
                    audio_track_id=audio.id,
                    bpm=120.0,
                    beat_positions=json.dumps([0.0, 1.0, 2.0, 3.0]),
                ),
                TimelineEntry(
                    project_id=project.id,
                    track="audio",
                    media_id=audio.id,
                    start_time=0.0,
                    end_time=8.0,
                ),
                TimelineEntry(
                    project_id=project.id,
                    track="video",
                    media_id=video.id,
                    start_time=0.0,
                    end_time=4.0,
                ),
            ]
        )
        pid = project.id
        session.commit()

    timeline = InteractiveTimeline()
    timeline.load_from_db(pid)
    deadline = time.time() + 5.0
    while time.time() < deadline:
        qapp.processEvents()
        if timeline._pending_entry_build is None and len(timeline.clip_items) >= 2:
            break
        time.sleep(0.01)

    assert len(timeline.clip_items) == 2
    assert any(item.title == "loaded audio" for item in timeline.clip_items)
    assert any(item.title == "video" for item in timeline.clip_items)
    assert len(timeline.waveform_items) == 1


def test_audio_waveform_paints_above_audio_clip(qapp) -> None:
    """B-471 live: waveform/beatgrid must not be hidden behind the blue clip bar."""
    timeline = InteractiveTimeline()
    clip = TimelineClipItem(
        entry_id=30,
        media_id=30,
        track_type="audio",
        title="audio with waveform",
        x=20.0,
        y=AUDIO_TRACK_Y,
        width=400.0,
        height=TRACK_HEIGHT,
        has_waveform=True,
        anchors=[],
    )
    timeline.scene().addItem(clip)
    timeline.clip_items.append(clip)
    waveform_data = SimpleNamespace(
        band_low="[0.1, 0.8, 0.2, 0.7]",
        band_mid="[0.2, 0.3, 0.4, 0.5]",
        band_high="[0.5, 0.4, 0.3, 0.2]",
        duration=20.0,
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
        dur=20.0,
        y=AUDIO_TRACK_Y,
    )
    waveform = next(item for item in timeline.waveform_items if isinstance(item, WaveformGraphicsItem))

    assert waveform.zValue() > clip.zValue()


def test_attached_waveform_is_not_stacked_behind_clip(qapp) -> None:
    """B-471 live: async waveform child must remain visible above the clip fill."""
    clip = TimelineClipItem(
        entry_id=31,
        media_id=31,
        track_type="audio",
        title="async waveform",
        x=0.0,
        y=AUDIO_TRACK_Y,
        width=400.0,
        height=TRACK_HEIGHT,
        has_waveform=True,
        anchors=[],
    )
    waveform = WaveformGraphicsItem(
        band_low=[0.1, 0.8, 0.2, 0.7],
        band_mid=[0.2, 0.3, 0.4, 0.5],
        band_high=[0.5, 0.4, 0.3, 0.2],
        duration=20.0,
        beat_positions=[0.0, 1.0, 2.0, 3.0],
        height=TRACK_HEIGHT,
        parent=clip,
    )
    waveform.setFlag(QGraphicsItem.GraphicsItemFlag.ItemStacksBehindParent, True)

    timeline = InteractiveTimeline()
    timeline._style_visible_waveform(waveform, parent_clip=clip)

    assert not bool(waveform.flags() & QGraphicsItem.GraphicsItemFlag.ItemStacksBehindParent)
    assert waveform.zValue() > clip.zValue()


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


def test_timeline_tracks_are_large_enough_for_readable_professional_waveform() -> None:
    """Notebook touchpad workflow needs readable lanes, not 50px micro tracks."""
    assert TRACK_HEIGHT >= 72


def test_timeline_toolbar_buttons_are_touchpad_sized(qapp) -> None:
    shell = TimelineShell()

    for button in (shell.btn_zoom_out, shell.btn_zoom_fit, shell.btn_zoom_reset, shell.btn_zoom_in):
        assert button.minimumWidth() >= 44
        assert button.minimumHeight() >= 36


def test_schnitt_tab_prioritizes_timeline_surface(qapp) -> None:
    """B-471 live: preview/cut list must not squeeze the timeline back to a strip."""
    tab = SchnittTabSchnitt()

    assert tab.timeline_shell.minimumHeight() >= 260
    assert tab.video_preview.maximumHeight() <= 240
    assert tab.cut_list_panel.maximumHeight() <= 140
