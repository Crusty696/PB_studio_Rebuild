"""Tests fuer Phase-5 UI-Widgets — Service-Anbindung + Signals.

CPU-only, kein interaktiver Test (kein .exec()).
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from PySide6.QtCore import QCoreApplication, QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication

from services.brain_v3.brain_v3_service import BrainV3Service
from services.brain_v3.context_resolver import CutContext
from services.brain_v3.schemas.brain_v3_schemas import FeedbackRequest
from services.brain_v3.schemas.brain_v3_schemas import (
    LearningSampleCut,
    LearningSessionResponse,
)


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture
def isolated_appdata(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    yield tmp_path


# ---- Stats-Panel -------------------------------------------------------
def test_stats_panel_initial_render(qt_app, isolated_appdata):
    from ui.widgets.brain_v3_stats_panel import BrainV3StatsPanel
    svc = BrainV3Service()
    panel = BrainV3StatsPanel(service=svc, auto_refresh_ms=10_000)
    panel.refresh()  # synchron
    assert "Total Klicks: 0" in panel._lbl_total_clicks.text()
    assert "0/17" in panel._lbl_learned.text()
    assert "Cold-Start: 17" in panel._lbl_learned.text()
    panel.deleteLater()


def test_stats_panel_after_feedback_shows_learning(qt_app, isolated_appdata):
    from ui.widgets.brain_v3_stats_panel import BrainV3StatsPanel
    svc = BrainV3Service()
    for _ in range(10):
        svc.feedback(FeedbackRequest(cut_id=1, rating="perfect"))
    panel = BrainV3StatsPanel(service=svc, auto_refresh_ms=10_000)
    panel.refresh()
    assert "17/17" in panel._lbl_learned.text() or "/17" in panel._lbl_learned.text()
    assert panel._tree_pos.topLevelItemCount() > 0
    panel.deleteLater()


def test_stats_panel_auto_refresh_skips_hidden_panel(qt_app):
    from ui.widgets.brain_v3_stats_panel import BrainV3StatsPanel

    class SlowStatsService:
        def __init__(self) -> None:
            self.calls = 0

        def stats(self):
            self.calls += 1
            return SimpleNamespace(
                total_clicks=0,
                learned_axes=0,
                cold_start_axes=17,
                last_feedback_at=None,
                top_positive_buckets=[],
                top_negative_buckets=[],
            )

    svc = SlowStatsService()
    panel = BrainV3StatsPanel(service=svc, auto_refresh_ms=10_000)
    try:
        panel._refresh_if_visible()
    finally:
        panel.deleteLater()

    assert svc.calls == 0


# ---- Feedback-Popup ----------------------------------------------------
def test_feedback_popup_submits(qt_app, isolated_appdata):
    from ui.widgets.brain_v3_feedback_popup import BrainV3FeedbackPopup
    svc = BrainV3Service()
    received: list[tuple[int, str, int]] = []
    popup = BrainV3FeedbackPopup(
        cut_id=42, service=svc, context=CutContext(),
    )
    popup.feedback_submitted.connect(
        lambda cid, rating, nb: received.append((cid, rating, nb))
    )
    popup._submit("perfect")
    assert received == [(42, "perfect", 102)]
    popup.deleteLater()


def test_feedback_popup_all_4_ratings(qt_app, isolated_appdata):
    from ui.widgets.brain_v3_feedback_popup import (
        BrainV3FeedbackPopup,
        FEEDBACK_BUTTONS,
    )
    svc = BrainV3Service()
    for rating, _, _ in FEEDBACK_BUTTONS:
        popup = BrainV3FeedbackPopup(cut_id=1, service=svc, context=CutContext())
        popup._submit(rating)
        popup.deleteLater()
    # alle 4 Klicks angekommen — stats sollten total_clicks zeigen
    assert svc.stats().total_clicks > 0


def test_confidence_color_extremes(qt_app):
    from ui.widgets.brain_v3_feedback_popup import confidence_color_hex
    red = confidence_color_hex(0.0)
    green = confidence_color_hex(1.0)
    yellow = confidence_color_hex(0.5)
    assert red.startswith("#ff")  # red dominant
    assert green.startswith("#00ff")  # green dominant
    assert yellow.startswith("#ffff")


# ---- Learning-Session-Dialog -------------------------------------------
def test_learning_dialog_loads_samples(qt_app, isolated_appdata):
    from ui.widgets.brain_v3_learning_dialog import BrainV3LearningSessionDialog
    svc = BrainV3Service()
    # einige Klicks damit Sampler etwas zurueckliefert
    for _ in range(2):
        svc.feedback(FeedbackRequest(cut_id=1, rating="perfect"))
    for _ in range(2):
        svc.feedback(FeedbackRequest(cut_id=2, rating="no_match"))
    dlg = BrainV3LearningSessionDialog(service=svc, n_samples=10)
    assert dlg._list.count() > 0
    dlg.deleteLater()


def test_learning_dialog_empty_store_handled(qt_app, isolated_appdata):
    from ui.widgets.brain_v3_learning_dialog import BrainV3LearningSessionDialog
    svc = BrainV3Service(project_root=isolated_appdata / "empty_project")
    dlg = BrainV3LearningSessionDialog(service=svc, n_samples=15)
    assert dlg._list.count() == 0
    assert "0 Stichproben" in dlg._lbl_status.text()
    dlg.deleteLater()


def test_learning_dialog_loads_audio_video_preview(qt_app, tmp_path, monkeypatch):
    from ui.widgets.brain_v3_learning_dialog import BrainV3LearningSessionDialog
    from ui.widgets.video_preview import VideoPreviewWidget

    played_from: list[float] = []
    monkeypatch.setattr(
        VideoPreviewWidget,
        "_extract_and_show_frame",
        lambda self, time_sec, vf_extra="": self.setText("frame loaded"),
    )
    monkeypatch.setattr(
        VideoPreviewWidget,
        "play_from",
        lambda self, time_sec: played_from.append(float(time_sec)),
    )
    audio = tmp_path / "sample.mp3"
    video = tmp_path / "sample.mp4"
    audio.write_bytes(b"id3")
    video.write_bytes(b"fake")

    class _PreviewService:
        def learning_session(self, n=15):
            return LearningSessionResponse(
                samples=[
                    LearningSampleCut(
                        cut_id=7,
                        audio_position_s=12.5,
                        video_position_s=8.5,
                        preview_duration_s=4.0,
                        clip_id=3,
                        audio_preview_path=str(audio),
                        video_preview_path=str(video),
                        uncertainty=0.42,
                    )
                ],
                requested_n=n,
                available_n=1,
            )

    dlg = BrainV3LearningSessionDialog(service=_PreviewService(), n_samples=1)
    assert dlg._list.count() == 1
    assert dlg._video_preview._current_path == str(video)
    assert Path(dlg._audio_player.source().toLocalFile()) == audio
    assert dlg._lbl_preview.text().startswith("Preview: Cut #7")
    assert dlg._btn_preview_play.isEnabled()
    dlg._toggle_preview()
    assert played_from == [8.5]
    dlg.deleteLater()


# ---- Timeline-Integration ----------------------------------------------
class _FakeBrainV3TimelineService:
    def __init__(self):
        self.calls: list[tuple[int, str, object]] = []

    def feedback(self, request, context=None):
        self.calls.append((int(request.cut_id), str(request.rating), context))
        return SimpleNamespace(n_buckets_updated=102)


def test_timeline_clip_item_submits_brain_v3_feedback(qt_app):
    from ui.timeline import TimelineClipItem

    svc = _FakeBrainV3TimelineService()
    ctx = CutContext(audio_section_type="drop")
    item = TimelineClipItem(
        entry_id=77,
        media_id=12,
        track_type="video",
        title="clip",
        x=0,
        y=0,
        width=100,
        height=50,
        anchors=[],
    )

    item.set_brain_v3_feedback(service=svc, context=ctx)
    item.set_brain_v3_cut_id(901)
    assert item._submit_brain_v3_feedback("perfect") == 102
    assert svc.calls == [(901, "perfect", ctx)]


def test_timeline_clip_item_confidence_bar_updates(qt_app):
    from ui.timeline import TimelineClipItem

    item = TimelineClipItem(
        entry_id=78,
        media_id=13,
        track_type="video",
        title="clip",
        x=0,
        y=0,
        width=120,
        height=50,
        anchors=[],
    )

    item.set_brain_v3_confidence(0.75)
    assert item._brain_v3_confidence_bar.isVisible()
    assert item._brain_v3_confidence_bar.rect().width() == 120

    item.set_brain_v3_confidence(None)
    assert not item._brain_v3_confidence_bar.isVisible()


def test_interactive_timeline_brain_v3_hotkey_submits_selected_clip(qt_app):
    from ui.timeline import InteractiveTimeline, TimelineClipItem

    svc = _FakeBrainV3TimelineService()
    ctx = CutContext(audio_section_type="drop")
    timeline = InteractiveTimeline()
    item = TimelineClipItem(
        entry_id=79,
        media_id=14,
        track_type="video",
        title="clip",
        x=0,
        y=0,
        width=120,
        height=50,
        anchors=[],
    )
    timeline._scene.addItem(item)
    timeline.clip_items.append(item)
    timeline.set_brain_v3_feedback_service(svc, context=ctx)
    item.setSelected(True)

    event = QKeyEvent(
        QEvent.Type.KeyPress,
        Qt.Key.Key_2,
        Qt.KeyboardModifier.NoModifier,
    )
    timeline.keyPressEvent(event)

    assert svc.calls == [(79, "fits", ctx)]
    assert event.isAccepted()
    timeline.deleteLater()


def test_interactive_timeline_applies_brain_v3_state_metadata(qt_app):
    from services.brain_v3.timeline_state import BrainV3TimelineCutMeta
    from ui.timeline import InteractiveTimeline

    timeline = InteractiveTimeline()
    timeline._brain_v3_timeline_meta = {
        (14, 1000): BrainV3TimelineCutMeta(
            cut_id=901,
            clip_id=14,
            start_time=1.0,
            confidence=0.66,
        )
    }
    entry = SimpleNamespace(id=79, media_id=14, track="video", start_time=1.0)
    clip = SimpleNamespace(file_path="C:/tmp/clip.mp4", duration=3.0)

    timeline._build_entries([entry], {}, {14: clip}, {})

    item = timeline.clip_items[0]
    assert item._brain_v3_cut_id == 901
    assert item._brain_v3_confidence == pytest.approx(0.66)
    assert item._brain_v3_confidence_bar.isVisible()
    timeline.deleteLater()
