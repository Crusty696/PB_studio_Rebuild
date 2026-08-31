"""STAB-5 Controls #191-#222: Schnitt & Workflow Controls elementgenau belegen.

Deckt folgende Controls ab:
  - SchnittEditorView (#191-#194)
  - SchnittEmptyView (#195-#196)
  - SchnittLoadingView (#197)
  - SchnittTabPacingAnker (#198-#210)
  - (#211-#212 entfallen mit dem RL-Teil, siehe B-927)
  - SchnittTabSchnitt (#213-#214)
  - TimelineShell (#215-#219)
  - ProjectDashboard (#220-#222)
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

from ui.workspaces.schnitt.editor_view import SchnittEditorView
from ui.workspaces.schnitt.empty_view import SchnittEmptyView
from ui.workspaces.schnitt.loading_view import SchnittLoadingView
from ui.workspaces.schnitt.tab_pacing_anker import SchnittTabPacingAnker
from ui.workspaces.schnitt.tab_schnitt import SchnittTabSchnitt
from ui.workspaces.schnitt.timeline_shell import TimelineShell
from ui.workspaces.workflow_pages import ProjectDashboard


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


# ── SchnittEditorView #191-#194 ───────────────────────────────────────────────


def test_control_191_audio_combo_selection() -> None:
    """#191 editor_view.py:69 self.audio_combo: QComboBox für Audio-Track-Auswahl."""
    app = _qapp()
    view = SchnittEditorView()
    try:
        combo = view.audio_combo
        assert combo.isVisibleTo(view) is True
        assert combo.isEnabled() is True

        combo.addItem("Track 01.mp3", "data_01")
        combo.addItem("Track 02.mp3", "data_02")
        combo.setCurrentIndex(1)
        app.processEvents()

        assert combo.currentIndex() == 1
        assert combo.currentText() == "Track 02.mp3"
    finally:
        _cleanup(app, view)


def test_control_192_video_combo_selection() -> None:
    """#192 editor_view.py:79 self.video_combo: QComboBox für Video-Clip-Auswahl."""
    app = _qapp()
    view = SchnittEditorView()
    try:
        combo = view.video_combo
        assert combo.isVisibleTo(view) is True
        assert combo.isEnabled() is True

        combo.addItem("Clip A.mp4", "clip_a")
        combo.addItem("Clip B.mp4", "clip_b")
        combo.setCurrentIndex(1)
        app.processEvents()

        assert combo.currentIndex() == 1
        assert combo.currentText() == "Clip B.mp4"
    finally:
        _cleanup(app, view)


def test_control_193_btn_generate_triggers_click() -> None:
    """#193 editor_view.py:90 self.btn_generate: Timeline generieren."""
    app = _qapp()
    view = SchnittEditorView()
    try:
        clicked = []
        view.btn_generate.clicked.connect(lambda: clicked.append(True))

        btn = view.btn_generate
        assert btn.isVisibleTo(view) is True
        assert btn.isEnabled() is True

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(clicked) == 1
    finally:
        _cleanup(app, view)


def test_control_194_btn_auto_edit_triggers_click() -> None:
    """#194 editor_view.py:107 self.btn_auto_edit: Auto-Edit starten."""
    app = _qapp()
    view = SchnittEditorView()
    try:
        clicked = []
        view.btn_auto_edit.clicked.connect(lambda: clicked.append(True))

        btn = view.btn_auto_edit
        assert btn.isVisibleTo(view) is True
        assert btn.isEnabled() is True

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(clicked) == 1
    finally:
        _cleanup(app, view)


# ── SchnittEmptyView #195-#196 ────────────────────────────────────────────────


def test_control_195_preset_button_emits_signal() -> None:
    """#195 empty_view.py:47 btn: Preset-Button 'Techno' Klick sendet preset_selected Signal."""
    app = _qapp()
    view = SchnittEmptyView()
    try:
        emitted = []
        view.preset_selected.connect(lambda key: emitted.append(key))

        btn = view._buttons["Techno"]
        assert btn.isVisibleTo(view) is True
        assert btn.isEnabled() is True

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert emitted == ["Techno"]
    finally:
        _cleanup(app, view)


def test_control_196_btn_custom_emits_custom_clicked() -> None:
    """#196 empty_view.py:52 self.btn_custom: Eigene Einstellungen… Klick sendet custom_clicked Signal."""
    app = _qapp()
    view = SchnittEmptyView()
    try:
        emitted = []
        view.custom_clicked.connect(lambda: emitted.append(True))

        btn = view.btn_custom
        assert btn.isVisibleTo(view) is True
        assert btn.isEnabled() is True

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(emitted) == 1
    finally:
        _cleanup(app, view)


# ── SchnittLoadingView #197 ───────────────────────────────────────────────────


def test_control_197_btn_cancel_loading_emits_cancel_requested() -> None:
    """#197 loading_view.py:54 self.btn_cancel: Abbrechen sendet cancel_requested Signal."""
    app = _qapp()
    view = SchnittLoadingView()
    try:
        emitted = []
        view.cancel_requested.connect(lambda: emitted.append(True))

        btn = view.btn_cancel
        assert btn.isVisibleTo(view) is True
        assert btn.isEnabled() is True

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(emitted) == 1
    finally:
        _cleanup(app, view)


# ── SchnittTabPacingAnker #198-#210 ───────────────────────────────────────────


def test_control_198_cut_rate_combo_changes_index() -> None:
    """#198 tab_pacing_anker.py:42 self.cut_rate_combo: QComboBox für Schnittdichte."""
    app = _qapp()
    view = SchnittTabPacingAnker()
    try:
        combo = view.cut_rate_combo
        assert combo.isVisibleTo(view) is True
        assert combo.isEnabled() is True

        combo.setCurrentIndex(0)  # "1 Beat"
        app.processEvents()

        assert combo.currentIndex() == 0
        assert combo.currentText() == "1 Beat"
    finally:
        _cleanup(app, view)


def test_control_199_style_combo_changes_index() -> None:
    """#199 tab_pacing_anker.py:60 self.style_combo: QComboBox für Stilprofil."""
    app = _qapp()
    view = SchnittTabPacingAnker()
    try:
        combo = view.style_combo
        assert combo.isVisibleTo(view) is True
        assert combo.isEnabled() is True

        combo.setCurrentIndex(1)  # "Techno"
        app.processEvents()

        assert combo.currentIndex() == 1
        assert combo.currentText() == "Techno"
    finally:
        _cleanup(app, view)


def test_control_200_breakdown_combo_changes_index() -> None:
    """#200 tab_pacing_anker.py:73 self.breakdown_combo: QComboBox für Breakdown-Steuerung."""
    app = _qapp()
    view = SchnittTabPacingAnker()
    try:
        combo = view.breakdown_combo
        assert combo.isVisibleTo(view) is True
        assert combo.isEnabled() is True

        combo.setCurrentIndex(1)  # "force16"
        app.processEvents()

        assert combo.currentIndex() == 1
        assert combo.currentText() == "force16"
    finally:
        _cleanup(app, view)


def test_control_201_transition_combo_changes_index() -> None:
    """#201 tab_pacing_anker.py:115 self.transition_combo: QComboBox für Übergänge."""
    app = _qapp()
    view = SchnittTabPacingAnker()
    try:
        combo = view.transition_combo
        assert combo.isVisibleTo(view) is True
        assert combo.isEnabled() is True

        combo.setCurrentIndex(0)  # "Automatische Crossfades (experimentell)"
        app.processEvents()

        assert combo.currentIndex() == 0
    finally:
        _cleanup(app, view)


def test_control_202_chk_studio_brain_toggled() -> None:
    """#202 tab_pacing_anker.py:153 self.chk_studio_brain: Studio-Brain Checkbox Toggle."""
    app = _qapp()
    view = SchnittTabPacingAnker()
    try:
        chk = view.chk_studio_brain
        assert chk.isVisibleTo(view) is True

        initial_state = chk.isChecked()
        chk.click()
        app.processEvents()

        assert chk.isChecked() != initial_state
    finally:
        _cleanup(app, view)


def test_control_203_chk_llm_strategist_toggled() -> None:
    """#203 tab_pacing_anker.py:162 self.chk_llm_strategist: LLM-Strategist Checkbox."""
    app = _qapp()
    view = SchnittTabPacingAnker()
    try:
        chk = view.chk_llm_strategist
        assert chk is not None

        if chk.isEnabled():
            initial_state = chk.isChecked()
            chk.click()
            app.processEvents()
            assert chk.isChecked() != initial_state
        else:
            assert chk.toolTip().startswith("Deaktiviert: Ollama")
    finally:
        _cleanup(app, view)


def test_control_204_chk_llm_pacing_toggled() -> None:
    """#204 tab_pacing_anker.py:169 self.chk_llm_pacing: LLM-EDL-Pacing Checkbox."""
    app = _qapp()
    view = SchnittTabPacingAnker()
    try:
        chk = view.chk_llm_pacing
        assert chk is not None

        if chk.isEnabled():
            initial_state = chk.isChecked()
            chk.click()
            app.processEvents()
            assert chk.isChecked() != initial_state
        else:
            assert chk.toolTip().startswith("Deaktiviert: Ollama")
    finally:
        _cleanup(app, view)


def test_control_205_btn_ab_compare_opens_dialog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#205 tab_pacing_anker.py:213 self.btn_ab_compare: A/B-Gewichte testen Button."""
    app = _qapp()
    view = SchnittTabPacingAnker()
    try:
        opened = []
        monkeypatch.setattr(view, "_open_ab_compare", lambda: opened.append(True))

        btn = view.btn_ab_compare
        assert btn.isVisibleTo(view) is True
        assert btn.isEnabled() is True

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(opened) == 1
    finally:
        _cleanup(app, view)


def test_control_206_btn_regenerate_triggers_click() -> None:
    """#206 tab_pacing_anker.py:228 self.btn_regenerate: Neu generieren Button."""
    app = _qapp()
    view = SchnittTabPacingAnker()
    try:
        clicked = []
        view.btn_regenerate.clicked.connect(lambda: clicked.append(True))

        btn = view.btn_regenerate
        assert btn.isVisibleTo(view) is True
        assert btn.isEnabled() is True

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(clicked) == 1
    finally:
        _cleanup(app, view)


def test_control_207_btn_add_anchor_triggers_click() -> None:
    """#207 tab_pacing_anker.py:287 self.btn_add_anchor: + Anker Button."""
    app = _qapp()
    view = SchnittTabPacingAnker()
    try:
        clicked = []
        view.btn_add_anchor.clicked.connect(lambda: clicked.append(True))

        btn = view.btn_add_anchor
        assert btn.isVisibleTo(view) is True
        assert btn.isEnabled() is True

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(clicked) == 1
    finally:
        _cleanup(app, view)


def test_control_208_btn_remove_anchor_triggers_click() -> None:
    """#208 tab_pacing_anker.py:294 self.btn_remove_anchor: − Anker Button."""
    app = _qapp()
    view = SchnittTabPacingAnker()
    try:
        clicked = []
        view.btn_remove_anchor.clicked.connect(lambda: clicked.append(True))

        btn = view.btn_remove_anchor
        assert btn.isVisibleTo(view) is True
        assert btn.isEnabled() is True

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(clicked) == 1
    finally:
        _cleanup(app, view)


def test_control_209_btn_sync_anchors_triggers_click() -> None:
    """#209 tab_pacing_anker.py:301 self.btn_sync_anchors: Sync Button."""
    app = _qapp()
    view = SchnittTabPacingAnker()
    try:
        clicked = []
        view.btn_sync_anchors.clicked.connect(lambda: clicked.append(True))

        btn = view.btn_sync_anchors
        assert btn.isVisibleTo(view) is True
        assert btn.isEnabled() is True

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(clicked) == 1
    finally:
        _cleanup(app, view)


def test_control_210_btn_learn_ai_triggers_click() -> None:
    """#210 tab_pacing_anker.py:314 self.btn_learn_ai: Als KI-Lernregel speichern Button."""
    app = _qapp()
    view = SchnittTabPacingAnker()
    try:
        clicked = []
        view.btn_learn_ai.clicked.connect(lambda: clicked.append(True))

        btn = view.btn_learn_ai
        assert btn.isVisibleTo(view) is True
        assert btn.isEnabled() is True

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(clicked) == 1
    finally:
        _cleanup(app, view)


# ── #211-#212 entfallen ──────────────────────────────────────────────────────
# B-927 (Userentscheidung 2026-08-31): Die Kontrollen #211 btn_thumbs_up und
# #212 btn_thumbs_down existieren nicht mehr. Der Tab "RL & Notes" hiess nach
# dem Entfernen des wirkungslosen RL-Teils "Notizen"; die Notizen selbst sind
# unveraendert und in tests/ui/test_subtab_notizen.py abgedeckt.


# ── SchnittTabSchnitt #213-#214 ───────────────────────────────────────────────


def test_control_213_btn_play_toggles_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#213 tab_schnitt.py:53 self.btn_play: ▶ Button ruft video_preview.toggle_play auf."""
    app = _qapp()
    view = SchnittTabSchnitt()
    try:
        called = []
        monkeypatch.setattr(view.video_preview, "toggle_play", lambda: called.append(True))

        btn = view.btn_play
        assert btn.isVisibleTo(view) is True
        assert btn.isEnabled() is True

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(called) == 1
    finally:
        _cleanup(app, view)


def test_control_214_btn_stop_stops_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#214 tab_schnitt.py:58 self.btn_stop: ■ Button ruft video_preview.stop auf."""
    app = _qapp()
    view = SchnittTabSchnitt()
    try:
        called = []
        monkeypatch.setattr(view.video_preview, "stop", lambda: called.append(True))

        btn = view.btn_stop
        assert btn.isVisibleTo(view) is True
        assert btn.isEnabled() is True

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(called) == 1
    finally:
        _cleanup(app, view)


# ── TimelineShell #215-#219 ───────────────────────────────────────────────────


def test_control_215_btn_snapshots_button_active() -> None:
    """#215 timeline_shell.py:71 self.btn_snapshots: QToolButton Snapshots."""
    app = _qapp()
    shell = TimelineShell()
    try:
        btn = shell.btn_snapshots
        assert btn.isVisibleTo(shell) is True
        assert btn.isEnabled() is True
        assert btn.text() == "Snapshots"
    finally:
        _cleanup(app, shell)


def test_control_216_btn_zoom_out_triggers_zoom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#216 timeline_shell.py:106 self.btn_zoom_out: Zoom Out Button."""
    app = _qapp()
    shell = TimelineShell()
    try:
        zoomed = []
        monkeypatch.setattr(shell, "_zoom_by", lambda factor: zoomed.append(factor))

        btn = shell.btn_zoom_out
        assert btn.isVisibleTo(shell) is True
        assert btn.isEnabled() is True

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(zoomed) == 1
        assert pytest.approx(zoomed[0], 0.01) == 1 / 1.15
    finally:
        _cleanup(app, shell)


def test_control_217_btn_zoom_fit_triggers_fit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#217 timeline_shell.py:111 self.btn_zoom_fit: Zoom Fit Button."""
    app = _qapp()
    shell = TimelineShell()
    try:
        fitted = []
        monkeypatch.setattr(shell, "_fit_to_content", lambda: fitted.append(True))

        btn = shell.btn_zoom_fit
        assert btn.isVisibleTo(shell) is True
        assert btn.isEnabled() is True

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(fitted) == 1
    finally:
        _cleanup(app, shell)


def test_control_218_btn_zoom_reset_triggers_reset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#218 timeline_shell.py:116 self.btn_zoom_reset: Zoom Reset (1:1) Button."""
    app = _qapp()
    shell = TimelineShell()
    try:
        reset = []
        monkeypatch.setattr(shell, "_reset_zoom", lambda: reset.append(True))

        btn = shell.btn_zoom_reset
        assert btn.isVisibleTo(shell) is True
        assert btn.isEnabled() is True

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(reset) == 1
    finally:
        _cleanup(app, shell)


def test_control_219_btn_zoom_in_triggers_zoom(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """#219 timeline_shell.py:121 self.btn_zoom_in: Zoom In Button."""
    app = _qapp()
    shell = TimelineShell()
    try:
        zoomed = []
        monkeypatch.setattr(shell, "_zoom_by", lambda factor: zoomed.append(factor))

        btn = shell.btn_zoom_in
        assert btn.isVisibleTo(shell) is True
        assert btn.isEnabled() is True

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(zoomed) == 1
        assert pytest.approx(zoomed[0], 0.01) == 1.15
    finally:
        _cleanup(app, shell)


# ── ProjectDashboard #220-#222 ────────────────────────────────────────────────


def test_control_220_btn_new_project_triggers_click() -> None:
    """#220 workflow_pages.py:77 self.btn_new_project: + Neues Projekt Button."""
    app = _qapp()
    dash = ProjectDashboard()
    try:
        clicked = []
        dash.btn_new_project.clicked.connect(lambda: clicked.append(True))

        btn = dash.btn_new_project
        assert btn.isVisibleTo(dash) is True
        assert btn.isEnabled() is True

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(clicked) == 1
    finally:
        _cleanup(app, dash)


def test_control_221_btn_open_project_triggers_click() -> None:
    """#221 workflow_pages.py:80 self.btn_open_project: Projekt oeffnen Button."""
    app = _qapp()
    dash = ProjectDashboard()
    try:
        clicked = []
        dash.btn_open_project.clicked.connect(lambda: clicked.append(True))

        btn = dash.btn_open_project
        assert btn.isVisibleTo(dash) is True
        assert btn.isEnabled() is True

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(clicked) == 1
    finally:
        _cleanup(app, dash)


def test_control_222_btn_next_step_emits_next_action() -> None:
    """#222 workflow_pages.py:98 self.btn_next_step: Projekt starten Button sendet action_requested Signal."""
    app = _qapp()
    dash = ProjectDashboard()
    try:
        emitted = []
        dash.action_requested.connect(lambda action: emitted.append(action))

        btn = dash.btn_next_step
        assert btn.isVisibleTo(dash) is True
        assert btn.isEnabled() is True

        QTest.mouseClick(btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert len(emitted) == 1
    finally:
        _cleanup(app, dash)
