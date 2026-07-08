"""NEUBAU-VOLLINTEGRATION T1.6: UI-Ehrlichkeit + Dead-End-Signals.

Vorher hatten feedback_event_emitted (Timeline), nodeSelected (Graph),
trackChanged (SteerTab), decisionSelected (Explorer), patternsReset
(MemoryTab), stats_refreshed (StatsPanel), session_finished
(LearningDialog) KEINEN einzigen connect. Jetzt: verdrahtet bzw. entfernt
(stats_refreshed).
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication


@pytest.fixture(scope="module", autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def test_stats_refreshed_signal_removed():
    """WIRE-011: stats_refreshed war zwecklos und ist entfernt."""
    from ui.widgets.brain_v3_stats_panel import BrainV3StatsPanel
    assert not hasattr(BrainV3StatsPanel, "stats_refreshed")


def test_stats_panel_wires_session_finished(monkeypatch):
    """WIRE-012: Lern-Session-Ende refresht das Stats-Panel sofort."""
    from ui.widgets.brain_v3_stats_panel import BrainV3StatsPanel

    class _FakeService:
        def stats(self):
            raise RuntimeError("kein Store im Test")

    panel = BrainV3StatsPanel(service=_FakeService(), auto_refresh_ms=999999)
    calls = {"n": 0}
    monkeypatch.setattr(panel, "refresh", lambda: calls.__setitem__("n", calls["n"] + 1))
    panel._on_learning_session_finished(7)
    assert calls["n"] == 1


def test_timeline_feedback_confirmation_connected():
    """feedback_event_emitted hat jetzt >=1 Subscriber und erzeugt eine
    sichtbare Console-Log-Bestaetigung."""
    from ui.timeline import InteractiveTimeline

    messages: list[str] = []
    tl = InteractiveTimeline(console_log=messages.append)
    tl.feedback_event_emitted.emit(123)
    assert any("Feedback" in m and "123" in m for m in messages)


def test_explorer_select_run_for_audio(monkeypatch):
    """WIRE-008-Consumer: Explorer kann Run per Audio-Track vorwaehlen."""
    from PySide6.QtCore import Qt
    from ui.widgets.pacing_decision_explorer import PacingDecisionExplorer

    ex = PacingDecisionExplorer(session_factory=None)
    ex.run_combo.addItem("Run 5 (audio=11, x)", 5)
    ex.run_combo.setItemData(0, 11, Qt.ItemDataRole.UserRole + 1)
    ex.run_combo.addItem("Run 9 (audio=22, y)", 9)
    ex.run_combo.setItemData(1, 22, Qt.ItemDataRole.UserRole + 1)

    assert ex.select_run_for_audio(22) is True
    assert ex.run_combo.currentIndex() == 1
    assert ex.select_run_for_audio(999) is False


def test_window_source_wires_dead_end_signals():
    """Quelltext-Vertrag: StudioBrainWindow verbindet decisionSelected,
    patternsReset, trackChanged und nodeSelected."""
    import inspect

    import ui.studio_brain_window as sbw
    src = inspect.getsource(sbw)
    assert "decisionSelected.connect(" in src
    assert "patternsReset.connect(self._on_patterns_reset)" in src
    assert "trackChanged.connect(self._on_steer_track_changed)" in src
    assert "nodeSelected.connect(self._on_graph_node_selected)" in src
