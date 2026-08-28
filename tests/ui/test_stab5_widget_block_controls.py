"""STAB-5 Controls #107-#124: Widget-Block elementgenau belegen.

Deckt folgende Widgets ab:
  - AnalysisStatusPanel (#107-#112)
  - BrainV3FeedbackPopup (#113-#115)
  - BrainV3LearningSessionDialog (#116-#119)
  - BrainV3StatsPanel (#120-#122)
  - CrossProjectReuseToast (#123)
  - CutListPanel (#124)
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence
from PySide6.QtGui import QShortcut
from PySide6.QtTest import QTest
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QPushButton,
    QWidget,
)

from ui.widgets.analysis_status_panel import AnalysisStatusPanel
from ui.widgets.brain_v3_feedback_popup import BrainV3FeedbackPopup
from ui.widgets.brain_v3_learning_dialog import BrainV3LearningSessionDialog
from ui.widgets.brain_v3_stats_panel import BrainV3StatsPanel
from ui.widgets.cross_project_reuse_toast import show_cross_project_reuse_toast
from ui.widgets.cut_list_panel import CutListPanel


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _cleanup(app: QApplication, *widgets: QWidget) -> None:
    for w in widgets:
        try:
            w.close()
            w.deleteLater()
        except Exception:
            pass
    app.processEvents()


# ── AnalysisStatusPanel #107-#112 ─────────────────────────────────────────────


def test_control_107_analysis_status_filter_combo_changes_filter() -> None:
    """#107 analysis_status_panel.py:169 filter_combo: IndexWechsel -> _on_filter_changed."""
    app = _qapp()
    panel = AnalysisStatusPanel()
    try:
        combo = panel.filter_combo
        assert combo.isVisibleTo(panel) is True
        assert combo.isEnabled() is True

        # Index 2 ist "Nur Fehler" -> filter_mode "error"
        combo.setCurrentIndex(2)
        app.processEvents()

        assert panel._filter_mode == "error"
    finally:
        _cleanup(app, panel)


def test_control_108_analysis_status_refresh_button_triggers_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#108 analysis_status_panel.py:254 btn_refresh: Klick -> refresh()."""
    app = _qapp()
    panel = AnalysisStatusPanel()
    try:
        refreshed = []
        monkeypatch.setattr(panel, "refresh", lambda: refreshed.append(True))

        btn = panel.btn_refresh
        assert btn.isVisibleTo(panel) is True
        assert btn.isEnabled() is True

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(refreshed) == 1
    finally:
        _cleanup(app, panel)


def test_control_109_analysis_status_retry_errors_button_triggers_retry_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#109 analysis_status_panel.py:278 btn_retry_errors: Klick -> _on_retry_all_errors()."""
    app = _qapp()
    panel = AnalysisStatusPanel()
    try:
        retried = []
        monkeypatch.setattr(
            panel, "_on_retry_all_errors", lambda: retried.append(True)
        )

        btn = panel.btn_retry_errors
        btn.setEnabled(True)  # Button fuer Test aktivieren

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(retried) == 1
    finally:
        _cleanup(app, panel)


def test_control_110_analysis_status_row_action_button_triggers_action(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#110 analysis_status_panel.py:495 row_action_btn: Klick -> _on_action_clicked."""
    app = _qapp()
    panel = AnalysisStatusPanel()
    try:
        clicked_steps = []
        panel.analysis_requested.connect(clicked_steps.append)

        # Mock-Status-Daten fuer 1 Zeile laden via _apply_status_data
        panel.set_media("video", 1)
        panel._apply_status_data({})
        app.processEvents()

        # Finde den erzeugten Button in Spalte 3 der Tabelle
        row_btn = None
        for r in range(panel.table.rowCount()):
            cell_widget = panel.table.cellWidget(r, 3)
            if cell_widget and isinstance(cell_widget, QPushButton):
                row_btn = cell_widget
                break

        assert row_btn is not None
        assert row_btn.text() in ("Starten", "Wiederholen")

        QTest.mouseClick(row_btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(clicked_steps) == 1
        assert clicked_steps[0] == "metadata_extract"
    finally:
        _cleanup(app, panel)


def test_controls_111_112_analysis_status_shortcuts_trigger_refresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#111 (F5) & #112 (Ctrl+R) in analysis_status_panel.py:640/644."""
    app = _qapp()
    panel = AnalysisStatusPanel()
    try:
        refreshed = 0

        def _count():
            nonlocal refreshed
            refreshed += 1

        monkeypatch.setattr(panel, "refresh", _count)

        shortcuts = panel.findChildren(QShortcut)
        assert len(shortcuts) >= 2

        f5_sc = [s for s in shortcuts if s.key().toString() == "F5"]
        ctrl_r_sc = [s for s in shortcuts if s.key().toString() in ("Ctrl+R", "Ctrl+r")]

        assert len(f5_sc) == 1
        assert len(ctrl_r_sc) == 1

        # Triggere den ersten Shortcut (F5)
        f5_sc[0].activated.emit()
        app.processEvents()
        assert refreshed == 1

        # Triggere den zweiten Shortcut (Ctrl+R)
        ctrl_r_sc[0].activated.emit()
        app.processEvents()
        assert refreshed == 2
    finally:
        _cleanup(app, panel)


# ── BrainV3FeedbackPopup #113-#115 ────────────────────────────────────────────


def test_control_113_feedback_popup_button_submits_rating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#113 brain_v3_feedback_popup.py:177 rating button: Klick -> _submit(r)."""
    app = _qapp()
    mock_brain = MagicMock()
    popup = BrainV3FeedbackPopup(cut_id=42, service=mock_brain)
    try:
        submitted = []
        monkeypatch.setattr(popup, "_submit", lambda r: submitted.append(r))

        buttons = [b for b in popup.findChildren(QPushButton) if b.text()]
        assert len(buttons) >= 4
        btn = buttons[0]

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(submitted) == 1
    finally:
        _cleanup(app, popup)


def test_control_114_feedback_popup_cancel_button_rejects() -> None:
    """#114 brain_v3_feedback_popup.py:189 cancel button: Klick -> reject."""
    app = _qapp()
    popup = BrainV3FeedbackPopup(cut_id=42)
    try:
        cancel_btns = [
            b for b in popup.findChildren(QPushButton) if "Abbrechen" in b.text()
        ]
        assert len(cancel_btns) == 1
        btn = cancel_btns[0]

        rejected = []
        popup.rejected.connect(lambda: rejected.append(True))

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(rejected) == 1
    finally:
        _cleanup(app, popup)


def test_control_115_feedback_popup_hotkeys_submit_rating(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#115 brain_v3_feedback_popup.py:200 hotkeys 1-4 submit rating."""
    app = _qapp()
    popup = BrainV3FeedbackPopup(cut_id=42)
    try:
        submitted = []
        monkeypatch.setattr(popup, "_submit", lambda r: submitted.append(r))

        shortcuts = popup.findChildren(QShortcut)
        assert len(shortcuts) >= 4

        # Triggere den ersten Hotkey ('1')
        shortcuts[0].activated.emit()
        app.processEvents()

        assert len(submitted) == 1
    finally:
        _cleanup(app, popup)


# ── BrainV3LearningSessionDialog #116-#119 ───────────────────────────────────


def test_controls_116_to_119_learning_dialog_buttons(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#116 (_btn_preview_play), #117 (_btn_preview_stop), #118 (_btn_open), #119 (_btn_close)."""
    app = _qapp()
    mock_brain = MagicMock()
    mock_brain.get_learning_candidates.return_value = []
    mock_brain._project_root = tmp_path
    dialog = BrainV3LearningSessionDialog(service=mock_brain)
    try:
        # Buttons fuer Interaktion aktivieren
        dialog._btn_preview_play.setEnabled(True)
        dialog._btn_preview_stop.setEnabled(True)
        dialog._btn_open.setEnabled(True)

        # #116 Preview Play
        toggled = []
        monkeypatch.setattr(dialog, "_toggle_preview", lambda: toggled.append(True))
        QTest.mouseClick(dialog._btn_preview_play, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert len(toggled) == 1

        # #117 Preview Stop
        stopped = []
        monkeypatch.setattr(dialog, "_stop_preview", lambda: stopped.append(True))
        QTest.mouseClick(dialog._btn_preview_stop, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert len(stopped) == 1

        # #118 Open/Bewerten
        opened = []
        monkeypatch.setattr(dialog, "_on_open_clicked", lambda: opened.append(True))
        QTest.mouseClick(dialog._btn_open, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert len(opened) == 1

        # #119 Close/Schliessen
        closed = []
        monkeypatch.setattr(dialog, "_on_close_clicked", lambda: closed.append(True))
        QTest.mouseClick(dialog._btn_close, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert len(closed) == 1
    finally:
        _cleanup(app, dialog)


# ── BrainV3StatsPanel #120-#122 ───────────────────────────────────────────────


def test_controls_120_to_122_stats_panel_buttons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#120 (_btn_refresh), #121 (_btn_learning), #122 (_btn_reset)."""
    app = _qapp()
    mock_brain = MagicMock()
    mock_brain.get_stats.return_value = {}
    panel = BrainV3StatsPanel(service=mock_brain)
    try:
        # #120 Refresh
        refreshed = []
        monkeypatch.setattr(panel, "refresh", lambda: refreshed.append(True))
        QTest.mouseClick(panel._btn_refresh, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert len(refreshed) == 1

        # #121 Learning Session
        learning_clicked = []
        monkeypatch.setattr(
            panel, "_on_learning_clicked", lambda: learning_clicked.append(True)
        )
        QTest.mouseClick(panel._btn_learning, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert len(learning_clicked) == 1

        # #122 Reset Hirn-Store
        reset_clicked = []
        monkeypatch.setattr(
            panel, "_on_reset_clicked", lambda: reset_clicked.append(True)
        )
        QTest.mouseClick(panel._btn_reset, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert len(reset_clicked) == 1
    finally:
        _cleanup(app, panel)


# ── CrossProjectReuseToast #123 ───────────────────────────────────────────────


def test_control_123_cross_project_reuse_checkbox() -> None:
    """#123 cross_project_reuse_toast.py:21 checkbox / Nicht mehr fragen."""
    app = _qapp()

    dialog = show_cross_project_reuse_toast(
        parent=None, message="Test-Hinweis", mute_key="test_mute_key"
    )
    try:
        assert dialog is not None
        chks = dialog.findChildren(QCheckBox)
        assert len(chks) == 1
        chk = chks[0]
        assert chk.text() == "Nicht mehr fragen"

        QTest.mouseClick(chk, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert chk.isChecked() is True
    finally:
        _cleanup(app, dialog)


# ── CutListPanel #124 ─────────────────────────────────────────────────────────


def test_control_124_cut_list_panel_refresh_button(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#124 cut_list_panel.py:64 btn_refresh / Aktualisieren."""
    app = _qapp()
    panel = CutListPanel()
    try:
        refreshed = []
        monkeypatch.setattr(panel, "refresh", lambda: refreshed.append(True))

        btn = panel.btn_refresh
        assert btn.isVisibleTo(panel) is True
        assert btn.isEnabled() is True

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(refreshed) == 1
    finally:
        _cleanup(app, panel)
