"""Tests fuer Phase-5 UI-Widgets — Service-Anbindung + Signals.

CPU-only, kein interaktiver Test (kein .exec()).
"""
from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from PySide6.QtCore import QCoreApplication, QEvent, QRectF, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication, QGraphicsRectItem

from services.brain.brain_v3_service import BrainV3Service
from services.brain.cold_start import BRIDGE_AXES
from services.brain.context_resolver import CutContext
from services.brain.schemas.brain_v3_schemas import FeedbackRequest
from services.brain.schemas.brain_v3_schemas import (
    LearningSampleCut,
    LearningSessionResponse,
)


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    yield app


def _process_until(predicate, timeout_ms: int = 8000) -> bool:
    """Pumpt die Qt-Event-Loop bis predicate True ist oder Timeout.

    Die Widgets laden/schreiben seit B-336 off-thread (run_worker). Tests
    muessen daher auf das finished-Signal des Workers warten statt synchron
    zu asserten.
    """
    import time
    deadline = time.monotonic() + timeout_ms / 1000.0
    while time.monotonic() < deadline:
        QCoreApplication.processEvents()
        if predicate():
            QCoreApplication.processEvents()
            return True
        time.sleep(0.01)
    QCoreApplication.processEvents()
    return bool(predicate())


def _assert_no_default_memory_updater() -> None:
    import workers.memory_updater as memory_updater

    assert memory_updater._default_memory_updater is None


@pytest.fixture(autouse=True)
def _reset_default_memory_updater():
    """``_default_memory_updater`` ist ein Modul-Singleton.

    Legt es ein frueher gelaufener Test an (z.B. ueber den
    App-Ende-Flush-Pfad) und raeumt nicht auf, sehen die drei
    ``_assert_no_default_memory_updater``-Tests hier einen Fremd-Updater
    und schlagen fehl — isoliert sind sie gruen, im Gesamtlauf rot.
    Vorbestehend (gegen Commit 4bacfb5 im Baseline-Worktree
    reproduziert, 3 failed), nicht durch die B-78x-Fixes verursacht.

    Der Reset stellt den Vertrag wieder her: gemessen wird, ob DIESER
    Testpfad einen Updater erzeugt — nicht, was Vorgaenger hinterliessen.
    """
    import workers.memory_updater as memory_updater

    memory_updater._default_memory_updater = None
    yield
    memory_updater._default_memory_updater = None


@pytest.fixture
def isolated_appdata(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "Roaming"))
    yield tmp_path


# ---- Stats-Panel -------------------------------------------------------
def test_stats_panel_initial_render(qt_app, isolated_appdata):
    from ui.widgets.brain_v3_stats_panel import BrainV3StatsPanel
    svc = BrainV3Service(pattern_notifier=lambda: None)
    panel = BrainV3StatsPanel(service=svc, auto_refresh_ms=10_000)
    panel.refresh()  # synchron
    assert "Total Klicks: 0" in panel._lbl_total_clicks.text()
    axis_count = len(BRIDGE_AXES)
    assert f"0/{axis_count}" in panel._lbl_learned.text()
    assert f"Cold-Start: {axis_count}" in panel._lbl_learned.text()
    assert panel._bar_learned.maximum() == axis_count
    panel.deleteLater()


def test_stats_panel_after_feedback_shows_learning(qt_app, isolated_appdata):
    from ui.widgets.brain_v3_stats_panel import BrainV3StatsPanel
    svc = BrainV3Service()
    for _ in range(10):
        svc.feedback(FeedbackRequest(cut_id=1, rating="perfect"))
    panel = BrainV3StatsPanel(service=svc, auto_refresh_ms=10_000)
    panel.refresh()
    assert f"{len(BRIDGE_AXES)}/{len(BRIDGE_AXES)}" in panel._lbl_learned.text()
    assert panel._tree_pos.topLevelItemCount() > 0
    panel.deleteLater()


def test_stats_panel_opens_learning_session_dialog(qt_app, isolated_appdata, monkeypatch):
    from ui.widgets import brain_v3_stats_panel
    from ui.widgets.brain_v3_stats_panel import BrainV3StatsPanel

    opened: list[object] = []

    class _FakeSignal:
        def connect(self, _callback):
            pass

    class _FakeLearningDialog:
        finished = _FakeSignal()
        # B-671: ``session_finished`` fehlte hier, seit WIRE-012 das Signal in
        # BrainV3StatsPanel verdrahtet hat (brain_v3_stats_panel.py:231 ->
        # brain_v3_learning_dialog.py:101). Der daraus folgende AttributeError
        # flog im Qt-Event-Loop und wurde still verschluckt — der Test blieb
        # gruen, pruefte die Verdrahtung aber faktisch nicht mehr. Erst der
        # pytest-qt-Hook macht solche Event-Loop-Exceptions sichtbar.
        session_finished = _FakeSignal()

        def __init__(self, service=None, n_samples=15, parent=None):
            opened.append((service, n_samples, parent))

        def isVisible(self):
            return False

        def open(self):
            return 0

    monkeypatch.setattr(
        brain_v3_stats_panel,
        "BrainV3LearningSessionDialog",
        _FakeLearningDialog,
    )

    svc = BrainV3Service()
    panel = BrainV3StatsPanel(service=svc, auto_refresh_ms=10_000)
    panel._btn_learning.click()

    assert opened == [(svc, 15, panel)]
    assert isinstance(panel._learning_dialog, _FakeLearningDialog)
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
                cold_start_axes=len(BRIDGE_AXES),
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
    svc = BrainV3Service(pattern_notifier=lambda: None)
    received: list[tuple[int, str, int]] = []
    popup = BrainV3FeedbackPopup(
        cut_id=42, service=svc, context=CutContext(),
    )
    popup.feedback_submitted.connect(
        lambda cid, rating, nb: received.append((cid, rating, nb))
    )
    popup._submit("perfect")
    assert _process_until(lambda: bool(received)), "Feedback nicht empfangen"
    assert received == [(42, "perfect", len(BRIDGE_AXES) * 6)]
    _assert_no_default_memory_updater()
    popup.deleteLater()


def test_feedback_popup_defers_default_service_until_submit(qt_app, monkeypatch):
    import ui.widgets.brain_v3_feedback_popup as feedback_popup

    constructed = []

    class FakeService:
        def __init__(self):
            constructed.append("init")

        def feedback(self, request, context=None, axis_contributions=None):
            class Resp:
                n_buckets_updated = 7

            return Resp()

    monkeypatch.setattr(feedback_popup, "BrainV3Service", FakeService)
    popup = feedback_popup.BrainV3FeedbackPopup(cut_id=42, context=CutContext())
    received: list[tuple[int, str, int]] = []
    popup.feedback_submitted.connect(
        lambda cid, rating, nb: received.append((cid, rating, nb))
    )

    assert constructed == []
    popup._submit("perfect")

    assert _process_until(lambda: bool(received)), "Feedback nicht empfangen"
    assert constructed == ["init"]
    assert received == [(42, "perfect", 7)]
    _assert_no_default_memory_updater()
    popup.deleteLater()


def test_popup_thread_local_service_preserves_pattern_notifier(isolated_appdata):
    """Injected B-737 notifier must survive the worker-thread service clone."""
    from ui.widgets.brain_v3_feedback_popup import build_thread_local_brain_service

    def notifier():
        return None

    src = BrainV3Service(pattern_notifier=notifier)
    cloned = build_thread_local_brain_service(src)
    try:
        assert cloned._pattern_notifier is notifier
        _assert_no_default_memory_updater()
    finally:
        src._weight_store.close()
        cloned._weight_store.close()


def test_feedback_popup_all_4_ratings(qt_app, isolated_appdata):
    from ui.widgets.brain_v3_feedback_popup import (
        BrainV3FeedbackPopup,
        FEEDBACK_BUTTONS,
    )
    svc = BrainV3Service(pattern_notifier=lambda: None)
    for rating, _, _ in FEEDBACK_BUTTONS:
        popup = BrainV3FeedbackPopup(cut_id=1, service=svc, context=CutContext())
        done: list = []
        popup.feedback_submitted.connect(lambda *a: done.append(a))
        popup._submit(rating)
        assert _process_until(lambda: bool(done)), f"Feedback {rating} nicht fertig"
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
    assert _process_until(lambda: dlg._list.count() > 0), "Samples nicht geladen"
    dlg.deleteLater()


def test_learning_dialog_empty_store_handled(qt_app, isolated_appdata):
    from ui.widgets.brain_v3_learning_dialog import BrainV3LearningSessionDialog
    svc = BrainV3Service(project_root=isolated_appdata / "empty_project")
    dlg = BrainV3LearningSessionDialog(service=svc, n_samples=15)
    assert _process_until(lambda: "0 Stichproben" in dlg._lbl_status.text()), \
        f"Status nicht aktualisiert: {dlg._lbl_status.text()!r}"
    assert dlg._list.count() == 0
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
    started_audio: list[tuple[Path, float, float]] = []
    monkeypatch.setattr(
        BrainV3LearningSessionDialog,
        "_start_audio_preview",
        lambda self, source, start_s, duration_s: started_audio.append(
            (Path(source), float(start_s), float(duration_s))
        ) or True,
    )

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
    assert _process_until(lambda: dlg._list.count() == 1), "Preview-Sample nicht geladen"
    assert dlg._video_preview._current_path == str(video)
    assert dlg._audio_preview_source == audio
    assert dlg._audio_preview_start_s == 12.5
    assert dlg._audio_preview_duration_s == 4.0
    assert dlg._lbl_preview.text().startswith("Preview: Cut #7")
    assert dlg._btn_preview_play.isEnabled()
    dlg._toggle_preview()
    assert played_from == []
    assert started_audio == [(audio, 12.5, 4.0)]
    dlg.deleteLater()


def test_video_preview_coalesces_frames_while_worker_running(qt_app, tmp_path):
    from ui.widgets.video_preview import VideoPreviewWidget

    video = tmp_path / "sample.mp4"
    video.write_bytes(b"fake")

    class _RunningThread:
        def isRunning(self):
            return True

    widget = VideoPreviewWidget()
    widget._current_path = str(video)
    widget._frame_thread = _RunningThread()

    widget._extract_and_show_frame(4.25)

    assert widget._pending_frame_request == (4.25, "")
    widget.deleteLater()


# ---- Timeline-Integration ----------------------------------------------
class _FakeBrainV3TimelineService:
    def __init__(self):
        self.calls: list[tuple[int, str, object]] = []

    def feedback(self, request, context=None, axis_contributions=None):
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


def test_interactive_timeline_accepts_focus_for_brain_v3_hotkeys(qt_app):
    from ui.timeline import InteractiveTimeline

    timeline = InteractiveTimeline()
    assert timeline.focusPolicy() == Qt.FocusPolicy.StrongFocus
    assert timeline.viewport().focusPolicy() == Qt.FocusPolicy.StrongFocus
    timeline.deleteLater()


def test_interactive_timeline_resolves_child_item_context_target(qt_app, monkeypatch):
    from ui.timeline import InteractiveTimeline, TimelineClipItem

    timeline = InteractiveTimeline()
    item = TimelineClipItem(
        entry_id=80,
        media_id=15,
        track_type="video",
        title="clip",
        x=0,
        y=0,
        width=120,
        height=50,
        anchors=[],
    )
    timeline._scene.addItem(item)
    monkeypatch.setattr(timeline, "itemAt", lambda _pos: item._right_handle)

    assert timeline._timeline_clip_item_at(object()) is item
    timeline.deleteLater()


def test_interactive_timeline_context_target_skips_parentless_overlay(qt_app, monkeypatch):
    from ui.timeline import InteractiveTimeline, TimelineClipItem

    timeline = InteractiveTimeline()
    item = TimelineClipItem(
        entry_id=81,
        media_id=16,
        track_type="video",
        title="clip",
        x=0,
        y=0,
        width=120,
        height=50,
        anchors=[],
    )
    overlay = QGraphicsRectItem(QRectF(0, 0, 120, 50))
    overlay.setZValue(3)
    timeline._scene.addItem(item)
    timeline._scene.addItem(overlay)
    monkeypatch.setattr(timeline, "itemAt", lambda _pos: overlay)
    monkeypatch.setattr(timeline, "items", lambda _pos: [overlay, item._right_handle])

    assert timeline._timeline_clip_item_at(object()) is item
    timeline.deleteLater()


def test_timeline_feedback_menu_and_popup_are_owned_by_timeline(qt_app, monkeypatch):
    import ui.timeline as timeline_module
    import ui.widgets.brain_v3_feedback_popup as feedback_popup_module
    from ui.timeline import InteractiveTimeline, TimelineClipItem

    timeline = InteractiveTimeline()
    item = TimelineClipItem(
        entry_id=82,
        media_id=17,
        track_type="video",
        title="clip",
        x=0,
        y=0,
        width=120,
        height=50,
        anchors=[],
    )
    timeline._scene.addItem(item)
    monkeypatch.setattr(timeline_module.QMenu, "popup", lambda *_args: None)

    item.show_context_menu_at(screen_pos=timeline.mapToGlobal(timeline.rect().center()), local_x=10)

    menu = item._context_menu
    assert menu.parent() is timeline
    menu.aboutToHide.emit()
    assert item._context_menu is menu
    QCoreApplication.processEvents()
    assert item._context_menu is None

    captured = {}

    class _Signal:
        def __init__(self):
            self._callback = None

        def connect(self, callback):
            self._callback = callback

        def emit(self, code):
            self._callback(code)

    class _FakeFeedbackPopup:
        def __init__(self, *args, parent=None, **kwargs):
            captured["parent"] = parent
            self.finished = _Signal()

        def isVisible(self):
            return False

        def open(self):
            captured["opened"] = True

        def deleteLater(self):
            captured["deleted"] = True

    monkeypatch.setattr(feedback_popup_module, "BrainV3FeedbackPopup", _FakeFeedbackPopup)
    monkeypatch.setattr(timeline, "_brain_v3_learning_signal", lambda _item: (None, {}))
    monkeypatch.setattr(item, "_brain_v3_pattern_feedback_target", lambda: None)

    item._open_brain_v3_feedback_popup()

    assert captured["parent"] is timeline
    assert captured["opened"] is True
    popup = item._brain_v3_feedback_popup
    popup.finished.emit(0)
    assert item._brain_v3_feedback_popup is popup
    QCoreApplication.processEvents()
    assert item._brain_v3_feedback_popup is None
    assert captured["deleted"] is True
    timeline.deleteLater()


def test_interactive_timeline_applies_brain_v3_state_metadata(qt_app):
    from services.brain.timeline_state import BrainV3TimelineCutMeta
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

    # M1 Timeline-Virtualisierung (D-066): _build_entries erzeugt fuer
    # Video-Clips nur einen leichten ClipRecord (Brain-Meta wird DORT schon
    # gesetzt, siehe rec.brain_cut_id/rec.brain_confidence). Das echte
    # TimelineClipItem entsteht erst lazy in _materialize_record, wenn der
    # Clip in den Viewport kommt (_update_virtualization). Nur Audio-Clips
    # werden beim Build sofort materialisiert. clip_items ist bei einem
    # frischen, ungezeigten Widget also leer — das ist keine Regression.
    assert timeline.clip_records[0].brain_cut_id == 901
    item = timeline._materialize_record(timeline.clip_records[0])
    assert item is not None
    assert item._brain_v3_cut_id == 901
    assert item._brain_v3_confidence == pytest.approx(0.66)
    assert item._brain_v3_confidence_bar.isVisible()
    timeline.deleteLater()


# ---- Tasten-Kollision 1-4 (2026-07-27) ----------------------------------
class _FakeFeedbackService:
    """Ersetzt FeedbackService in der Timeline; ohne DB."""

    _session_factory = None

    def __init__(self):
        self.ratings: list[tuple[int, int, int]] = []
        self.verdicts: list[tuple[int, int, str]] = []

    def record_rating(self, run_id, scene_id, rating):
        self.ratings.append((run_id, scene_id, rating))
        return SimpleNamespace(success=True, event_id=None, decision_id=1, error=None)

    def record_verdict(self, run_id, scene_id, verdict):
        self.verdicts.append((run_id, scene_id, verdict))
        return SimpleNamespace(success=True, event_id=None, decision_id=1, error=None)

    def record_brain_rating(self, run_id, scene_id, brain_rating):
        mapped = {
            "perfect": 5,
            "fits": 4,
            "not_quite": 2,
            "no_match": 1,
        }[brain_rating]
        self.ratings.append((run_id, scene_id, mapped))
        return SimpleNamespace(success=True, event_id=8, decision_id=1, error=None)


def _timeline_with_selected_clip(monkeypatch):
    from ui.timeline import InteractiveTimeline, TimelineClipItem

    brain = _FakeBrainV3TimelineService()
    fake_fb = _FakeFeedbackService()
    timeline = InteractiveTimeline()
    item = TimelineClipItem(
        entry_id=91, media_id=17, track_type="video", title="clip",
        x=0, y=0, width=120, height=50, anchors=[],
    )
    timeline._scene.addItem(item)
    timeline.clip_items.append(item)
    timeline.set_brain_v3_feedback_service(brain, context=CutContext(audio_section_type="drop"))
    timeline._feedback_service = fake_fb
    timeline.set_active_pacing_run(7)
    monkeypatch.setattr(timeline, "_resolve_scene_id", lambda _i: 42)
    # kein DB-Zugriff im Unit-Test
    monkeypatch.setattr(timeline, "_brain_v3_learning_signal", lambda _i: (None, {}))
    monkeypatch.setattr(timeline, "_notify_memory_updater", lambda: None)
    item.setSelected(True)
    return timeline, item, brain, fake_fb


def _press(timeline, key, modifier=Qt.KeyboardModifier.NoModifier):
    event = QKeyEvent(QEvent.Type.KeyPress, key, modifier)
    timeline.keyPressEvent(event)
    return event


def test_plain_digit_still_goes_to_brain_v3(qt_app, monkeypatch):
    timeline, _item, brain, fake_fb = _timeline_with_selected_clip(monkeypatch)
    _press(timeline, Qt.Key.Key_2)
    assert [c[1] for c in brain.calls] == ["fits"]
    assert fake_fb.ratings == [(7, 42, 4)]
    timeline.deleteLater()


def test_ctrl_digit_reaches_pacing_rating(qt_app, monkeypatch):
    """Vorher tot: 1-4 wurden von Brain-V3 abgefangen und mit return beendet."""
    timeline, _item, brain, fake_fb = _timeline_with_selected_clip(monkeypatch)
    for digit, key in (
        (1, Qt.Key.Key_1), (2, Qt.Key.Key_2), (3, Qt.Key.Key_3), (4, Qt.Key.Key_4),
    ):
        _press(timeline, key, Qt.KeyboardModifier.ControlModifier)
        assert fake_fb.ratings[-1] == (7, 42, digit)
    assert brain.calls == []
    timeline.deleteLater()


def test_plain_five_still_reaches_pacing_rating(qt_app, monkeypatch):
    timeline, _item, brain, fake_fb = _timeline_with_selected_clip(monkeypatch)
    _press(timeline, Qt.Key.Key_5)
    assert fake_fb.ratings == [(7, 42, 5)]
    assert brain.calls == []
    timeline.deleteLater()
