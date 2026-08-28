"""STAB-5 Controls #126-#140: MediaGrid, NavBar, Onboarding, PacingExplorer,
Stem-Widgets und TaskManagerDock elementgenau belegen."""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QWidget


def _qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


def _single_button(root: QWidget, text: str) -> QPushButton:
    buttons = [b for b in root.findChildren(QPushButton) if b.text() == text]
    assert len(buttons) == 1
    button = buttons[0]
    assert button.isVisibleTo(root) is True
    assert button.isEnabled() is True
    return button


# ── #126 MediaPoolGrid Sort-Combo ────────────────────────────────────────


def test_126_media_grid_sort_combo_triggers_apply_filter(monkeypatch) -> None:
    """Control #126: Sort-Combo (Video) mit korrekten Items; Auswahlwechsel
    erreicht _apply_filter (bound connect -> Klassen-Patch)."""
    app = _qapp()
    import ui.widgets.media_grid as mg

    calls: list[str] = []
    monkeypatch.setattr(
        mg.MediaPoolGrid, "_apply_filter", lambda self: calls.append("filter")
    )
    grid = mg.MediaPoolGrid(media_type="video")
    try:
        grid.show()
        app.processEvents()
        combo = grid._sort_combo
        assert combo.isVisibleTo(grid) is True
        assert combo.isEnabled() is True
        items = [combo.itemText(i) for i in range(combo.count())]
        assert items == ["Name", "Aufloesung", "FPS ▼"]

        calls.clear()
        combo.setCurrentIndex(1)
        app.processEvents()
        assert calls == ["filter"]
    finally:
        grid.deleteLater()
        app.processEvents()


# ── #127 WorkspaceNavBar ─────────────────────────────────────────────────


def test_127_nav_bar_button_switches_workspace() -> None:
    """Control #127: Workspace-Button emittiert Index und setzt Checked-Ring."""
    app = _qapp()
    from ui.widgets.nav_bar import WorkspaceNavBar

    bar = WorkspaceNavBar()
    try:
        bar.show()
        app.processEvents()
        emitted: list[int] = []
        bar.workspace_changed.connect(emitted.append)

        button = _single_button(bar, "SCHNITT")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert emitted == [2]
        assert [b.isChecked() for b in bar._buttons] == [
            False, False, True, False,
        ]
    finally:
        bar.deleteLater()
        app.processEvents()


# ── #128 OnboardingBanner ────────────────────────────────────────────────


def test_128_onboarding_dismiss_persists_and_hides() -> None:
    """Control #128: 'Verstanden' versteckt Banner, emittiert dismissed und
    persistiert in isolierten QSettings."""
    app = _qapp()
    from ui.widgets.onboarding_banner import OnboardingBanner

    org = ("PBStudioTest", "STAB5Banner")
    s = QSettings(*org)
    s.remove("window/onboarding/stab5-test")
    s.sync()
    banner = OnboardingBanner(
        "stab5-test", "Hinweistext", qsettings_org=org
    )
    try:
        banner.show()
        app.processEvents()
        assert banner.isVisible() is True
        emitted: list[bool] = []
        banner.dismissed.connect(lambda: emitted.append(True))

        button = _single_button(banner, "Verstanden")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert emitted == [True]
        assert banner.isVisible() is False
        assert QSettings(*org).value(
            "window/onboarding/stab5-test", False, type=bool
        ) is True
    finally:
        s.remove("window/onboarding/stab5-test")
        s.sync()
        banner.deleteLater()
        app.processEvents()


# ── #129-#132 PacingDecisionExplorer ─────────────────────────────────────


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeSession:
    """Minimaler SQL-Recorder fuer die drei Explorer-Queries."""

    def __init__(self, log: list):
        self._log = log

    def execute(self, stmt, params=None):
        sql = str(stmt)
        self._log.append((sql, dict(params or {})))
        if "FROM mem_pacing_run" in sql:
            return _FakeResult([
                (9, 1, "2026-08-27"),
                (8, 2, "2026-08-26"),
            ])
        if "FROM mem_decision WHERE run_id" in sql:
            return _FakeResult([
                (101, 0, 5, "drop", 0.8, None, "{}"),
            ])
        if "SELECT" in sql:
            return _FakeResult([])
        return _FakeResult([])

    def commit(self):
        self._log.append(("COMMIT", {}))

    def close(self):
        pass


def _explorer(log):
    from ui.widgets.pacing_decision_explorer import PacingDecisionExplorer

    explorer = PacingDecisionExplorer(
        session_factory=lambda: _FakeSession(log)
    )
    explorer.show()
    QApplication.processEvents()
    return explorer


def test_129_run_combo_change_loads_decisions() -> None:
    """Control #129: Run-Combo-Wechsel laedt Decisions des gewaehlten Runs."""
    app = _qapp()
    log: list = []
    explorer = _explorer(log)
    try:
        combo = explorer.run_combo
        assert combo.isVisibleTo(explorer) is True
        assert combo.isEnabled() is True
        assert combo.count() == 2
        assert explorer.table.rowCount() == 1  # Auto-Select Run 9

        log.clear()
        combo.setCurrentIndex(1)
        app.processEvents()
        decision_loads = [
            p for sql, p in log if "FROM mem_decision WHERE run_id" in sql
        ]
        assert decision_loads == [{"run_id": 8}]
    finally:
        explorer.deleteLater()
        app.processEvents()


def test_130_refresh_button_reloads_runs() -> None:
    """Control #130: 'Aktualisieren' laedt Run-Liste neu."""
    app = _qapp()
    log: list = []
    explorer = _explorer(log)
    try:
        button = _single_button(explorer, "Aktualisieren")
        log.clear()
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        run_loads = [sql for sql, _p in log if "FROM mem_pacing_run" in sql]
        assert len(run_loads) == 1
    finally:
        explorer.deleteLater()
        app.processEvents()


def test_131_132_verdict_buttons_write_verdict() -> None:
    """Controls #131/#132: Gut/Schlecht schreiben user_verdict der aktuellen
    Decision; ohne Auswahl kein Write."""
    app = _qapp()
    log: list = []
    explorer = _explorer(log)
    try:
        btn_good = _single_button(explorer, "👍 Gut")
        btn_bad = _single_button(explorer, "👎 Schlecht")

        explorer._current_decision_id = None
        log.clear()
        QTest.mouseClick(btn_good, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert [s for s, _p in log if "UPDATE mem_decision" in s] == []

        explorer._current_decision_id = 101
        log.clear()
        QTest.mouseClick(btn_good, Qt.MouseButton.LeftButton)
        app.processEvents()
        updates = [p for s, p in log if "UPDATE mem_decision" in s]
        assert updates == [{"verdict": "good", "id": 101}]
        assert ("COMMIT", {}) in log

        explorer._current_decision_id = 101
        log.clear()
        QTest.mouseClick(btn_bad, Qt.MouseButton.LeftButton)
        app.processEvents()
        updates = [p for s, p in log if "UPDATE mem_decision" in s]
        assert updates == [{"verdict": "bad", "id": 101}]
    finally:
        explorer.deleteLater()
        app.processEvents()


# ── #133/#134 StemMixerPanel ─────────────────────────────────────────────


def test_133_mute_button_emits_mute_toggled() -> None:
    """Control #133: 'M' toggelt Mute und emittiert (stem_name, True)."""
    app = _qapp()
    from ui.widgets.stem_mixer_panel import StemMixerPanel

    panel = StemMixerPanel("drums", "#ff0000", "DRUMS")
    try:
        panel.show()
        app.processEvents()
        emitted: list[tuple[str, bool]] = []
        panel.mute_toggled.connect(lambda n, c: emitted.append((n, c)))

        button = _single_button(panel, "M")
        assert button.isCheckable() is True
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert emitted == [("drums", True)]
        assert panel.is_muted is True
    finally:
        panel.deleteLater()
        app.processEvents()


def test_134_solo_button_checkable_and_exposed() -> None:
    """Control #134: 'S' ist checkbar; Consumer-API solo_btn zeigt exakt
    diesen Button (StemWorkspace verbindet toggled produktiv)."""
    app = _qapp()
    from ui.widgets.stem_mixer_panel import StemMixerPanel

    panel = StemMixerPanel("bass", "#00ff00", "BASS")
    try:
        panel.show()
        app.processEvents()
        button = _single_button(panel, "S")
        assert button is panel.solo_btn
        assert button.isCheckable() is True

        toggles: list[bool] = []
        panel.solo_btn.toggled.connect(toggles.append)
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert toggles == [True]
    finally:
        panel.deleteLater()
        app.processEvents()


# ── #135/#136 TransportBar ───────────────────────────────────────────────


def test_135_stop_button_emits_stop_requested() -> None:
    """Control #135: '■' emittiert stop_requested."""
    app = _qapp()
    from ui.widgets.stem_transport import TransportBar

    bar = TransportBar()
    try:
        bar.show()
        app.processEvents()
        emitted: list[str] = []
        bar.stop_requested.connect(lambda: emitted.append("stop"))

        button = _single_button(bar, "■")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert emitted == ["stop"]
    finally:
        bar.deleteLater()
        app.processEvents()


def test_136_play_button_toggles_play_pause_requests() -> None:
    """Control #136: '▶' emittiert play_requested; im Playing-Zustand
    pause_requested (Buttontext wechselt)."""
    app = _qapp()
    from ui.widgets.stem_transport import TransportBar

    bar = TransportBar()
    try:
        bar.show()
        app.processEvents()
        emitted: list[str] = []
        bar.play_requested.connect(lambda: emitted.append("play"))
        bar.pause_requested.connect(lambda: emitted.append("pause"))

        button = _single_button(bar, "▶")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert emitted == ["play"]

        bar.update_playback_state("playing")
        assert button.text() == "⏸"
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()
        assert emitted == ["play", "pause"]
    finally:
        bar.deleteLater()
        app.processEvents()


# ── #137 StemWorkspace Reset All ─────────────────────────────────────────


def test_137_reset_all_button_resets_tracks() -> None:
    """Control #137: 'Reset All' setzt Mute/Solo/Volume aller Tracks zurueck."""
    app = _qapp()
    from ui.widgets.stem_workspace import StemWorkspace

    ws = StemWorkspace()
    try:
        ws.show()
        app.processEvents()
        drums = ws._tracks["drums"]
        drums._mixer._mute_btn.setChecked(True)
        drums._mixer._vol_slider.setValue(30)
        ws._solo_active.add("drums")

        button = _single_button(ws, "Reset All")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert ws._solo_active == set()
        assert drums._mixer.is_muted is False
        assert drums._mixer._vol_slider.value() == 100
    finally:
        ws.deleteLater()
        app.processEvents()


# ── #138-#140 TaskManagerDock ────────────────────────────────────────────


class _FakeTM:
    def __init__(self, tasks):
        self.tasks = tasks
        self.cancelled: list[str] = []
        self.cleared = 0

    def get_task(self, tid):
        return self.tasks.get(tid)

    def cancel_task(self, tid):
        self.cancelled.append(tid)

    def clear_finished(self):
        self.cleared += 1


def _task_dock():
    from ui.widgets.task_manager_dock import TaskManagerDock

    dock = TaskManagerDock()
    dock.show()
    QApplication.processEvents()
    return dock


def _fake_task(name="Analyse", status="running", elapsed=5):
    return SimpleNamespace(
        name=name, status=status, elapsed=elapsed, progress=10, total=100,
        message="",
    )


def test_138_clear_button_removes_finished_rows() -> None:
    """Control #138: 'Fertige loeschen' entfernt beendete Rows und zeigt
    Leerzustand."""
    app = _qapp()
    dock = _task_dock()
    try:
        tm = _FakeTM({"t1": _fake_task(status="completed")})
        dock._tm = tm
        dock._on_task_added("t1")
        app.processEvents()
        assert "t1" in dock._task_rows
        assert dock._empty_label.isHidden() is True

        button = _single_button(dock, "Fertige loeschen")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert dock._task_rows == {}
        assert tm.cleared == 1
        assert dock._empty_label.isHidden() is False
    finally:
        dock.deleteLater()
        app.processEvents()


def test_139_header_cancel_cancels_longest_running() -> None:
    """Control #139: 'Abbrechen' cancelt den laengsten laufenden Task."""
    app = _qapp()
    dock = _task_dock()
    try:
        tm = _FakeTM({
            "kurz": _fake_task(elapsed=2),
            "lang": _fake_task(elapsed=50),
        })
        dock._tm = tm
        dock._on_task_added("kurz")
        dock._on_task_added("lang")
        app.processEvents()

        cancelled: list[str] = []
        dock.cancel_requested.connect(cancelled.append)
        button = _single_button(dock, "Abbrechen")
        QTest.mouseClick(button, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert tm.cancelled == ["lang"]
        assert cancelled == ["lang"]
    finally:
        dock.deleteLater()
        app.processEvents()


def test_140_row_cancel_button_cancels_specific_task() -> None:
    """Control #140: Zeilen-'✕' cancelt exakt den Task der Zeile (B-127)."""
    app = _qapp()
    dock = _task_dock()
    try:
        tm = _FakeTM({
            "a": _fake_task(elapsed=2),
            "b": _fake_task(elapsed=50),
        })
        dock._tm = tm
        dock._on_task_added("a")
        dock._on_task_added("b")
        app.processEvents()

        cancelled: list[str] = []
        dock.cancel_requested.connect(cancelled.append)
        row_btn = dock._task_rows["a"]["row_cancel_btn"]
        assert row_btn.text() == "✕"
        assert row_btn.isEnabled() is True
        QTest.mouseClick(row_btn, Qt.MouseButton.LeftButton)
        app.processEvents()

        assert tm.cancelled == ["a"]
        assert cancelled == ["a"]
    finally:
        dock.deleteLater()
        app.processEvents()
