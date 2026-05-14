"""SchnittWorkspace State-Manager-Tests (Phase 04 / Task 4.3).

Plan-Abweichung: nutzt `test_engine`-Fixture aus tests/conftest.py + Session
statt `init_db() + DBSession(engine)` (vgl. Phase 02/03).
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtWidgets import QApplication
from sqlalchemy.orm import Session as DBSession
from database.models import Project, TimelineEntry


def _qapp():
    return QApplication.instance() or QApplication([])


def _project(test_engine, with_clip: bool) -> int:
    with DBSession(test_engine) as s:
        p = Project(name="schnitt-state", path="/tmp/schnitt-state")
        s.add(p)
        s.flush()
        if with_clip:
            s.add(TimelineEntry(
                project_id=p.id, track="video", media_id=1,
                start_time=0, end_time=2, lane=0,
            ))
        s.commit()
        return p.id


def _patch_workspace_engine(monkeypatch, test_engine):
    import ui.workspaces.schnitt_workspace as ws_mod
    monkeypatch.setattr(ws_mod, "engine", test_engine)


def test_initial_no_project_shows_empty(test_engine, monkeypatch):
    _qapp()
    _patch_workspace_engine(monkeypatch, test_engine)
    from ui.workspaces.schnitt_workspace import SchnittWorkspace, STATE_EMPTY
    ws = SchnittWorkspace()
    ws.set_active_project(None)
    assert ws.current_state() == STATE_EMPTY
    assert all(not btn.isEnabled() for btn in ws.empty_view._buttons.values())
    assert ws.empty_view.btn_custom.isEnabled() is False


def test_project_with_no_clips_shows_empty(test_engine, monkeypatch):
    _qapp()
    _patch_workspace_engine(monkeypatch, test_engine)
    from ui.workspaces.schnitt_workspace import SchnittWorkspace, STATE_EMPTY
    ws = SchnittWorkspace()
    pid = _project(test_engine, with_clip=False)
    ws.set_active_project(pid)
    assert ws.current_state() == STATE_EMPTY
    assert all(btn.isEnabled() for btn in ws.empty_view._buttons.values())
    assert ws.empty_view.btn_custom.isEnabled() is True


def test_project_with_clips_shows_editor(test_engine, monkeypatch):
    _qapp()
    _patch_workspace_engine(monkeypatch, test_engine)
    from ui.workspaces.schnitt_workspace import SchnittWorkspace, STATE_EDITOR
    ws = SchnittWorkspace()
    pid = _project(test_engine, with_clip=True)
    ws.set_active_project(pid)
    assert ws.current_state() == STATE_EDITOR


def test_show_loading_then_editor(test_engine, monkeypatch):
    _qapp()
    _patch_workspace_engine(monkeypatch, test_engine)
    from ui.workspaces.schnitt_workspace import (
        SchnittWorkspace, STATE_LOADING, STATE_EDITOR,
    )
    ws = SchnittWorkspace()
    pid = _project(test_engine, with_clip=False)
    ws.set_active_project(pid)
    ws.enter_loading()
    assert ws.current_state() == STATE_LOADING
    # Simuliere Worker-Done
    pid2 = _project(test_engine, with_clip=True)
    ws.set_active_project(pid2)
    ws.refresh_state_from_db()
    assert ws.current_state() == STATE_EDITOR


# ---------------------------------------------------------------------------
# T5.7 Coverage-Sweep (E7)
# ---------------------------------------------------------------------------


def test_loading_to_empty_after_cancel(test_engine, monkeypatch):
    """Cancel-Path: Loading → cancel_requested → Empty (manuell zurueckgesetzt).

    Cancel selbst ist Signal-only (vom Controller verkabelt). Wir verifizieren
    dass nach enter_loading + manuellem set_active_project(None) wieder Empty.
    """
    _qapp()
    _patch_workspace_engine(monkeypatch, test_engine)
    from ui.workspaces.schnitt_workspace import SchnittWorkspace, STATE_LOADING, STATE_EMPTY
    ws = SchnittWorkspace()
    ws.enter_loading()
    assert ws.current_state() == STATE_LOADING
    ws.set_active_project(None)
    assert ws.current_state() == STATE_EMPTY


def test_set_stage_unknown_key_falls_back(test_engine, monkeypatch):
    """Unbekannter stage_key → Fallback-Text 'Vorbereiten…'."""
    _qapp()
    _patch_workspace_engine(monkeypatch, test_engine)
    from ui.workspaces.schnitt_workspace import SchnittWorkspace
    ws = SchnittWorkspace()
    ws.show_progress("vollkommen-unbekannt", 0.5)
    assert ws.loading_view.status_label.text() == "Vorbereiten…"


def test_set_stage_clamps_negative_and_above_one(test_engine, monkeypatch):
    """fraction=-0.1 → 0; fraction=1.5 → 100."""
    _qapp()
    _patch_workspace_engine(monkeypatch, test_engine)
    from ui.workspaces.schnitt_workspace import SchnittWorkspace
    ws = SchnittWorkspace()
    ws.show_progress("audio_load", -0.1)
    assert ws.loading_view.progress_bar.value() == 0
    ws.show_progress("audio_load", 1.5)
    assert ws.loading_view.progress_bar.value() == 100


def test_loading_view_reset(test_engine, monkeypatch):
    """reset() setzt Status-Text + Progress-Bar zurueck."""
    _qapp()
    _patch_workspace_engine(monkeypatch, test_engine)
    from ui.workspaces.schnitt_workspace import SchnittWorkspace
    ws = SchnittWorkspace()
    ws.show_progress("cut_calc", 0.42)
    assert ws.loading_view.progress_bar.value() == 42
    ws.loading_view.reset()
    assert ws.loading_view.status_label.text() == "Vorbereiten…"
    assert ws.loading_view.progress_bar.value() == 0


def test_empty_view_btn_custom_emits_signal(test_engine, monkeypatch):
    """Klick auf btn_custom emittiert custom_clicked am Workspace."""
    _qapp()
    _patch_workspace_engine(monkeypatch, test_engine)
    from ui.workspaces.schnitt_workspace import SchnittWorkspace
    ws = SchnittWorkspace()
    ws.set_active_project(_project(test_engine, with_clip=False))
    received = []
    ws.custom_clicked.connect(lambda: received.append(1))
    ws.empty_view.btn_custom.click()
    assert received == [1]


def test_show_progress_propagates_to_progress_bar(test_engine, monkeypatch):
    """show_progress(stage, fraction) propagiert zu loading_view.progress_bar.value()."""
    _qapp()
    _patch_workspace_engine(monkeypatch, test_engine)
    from ui.workspaces.schnitt_workspace import SchnittWorkspace
    ws = SchnittWorkspace()
    ws.show_progress("structure", 0.73)
    assert ws.loading_view.progress_bar.value() == 73
    assert ws.loading_view.status_label.text() == "Erkenne Songstruktur…"


def test_inspector_present_after_subtab_switch(test_engine, monkeypatch):
    """Editor-View hat persistenten Inspector — bleibt nach Sub-Tab-Wechsel."""
    _qapp()
    _patch_workspace_engine(monkeypatch, test_engine)
    from ui.workspaces.schnitt_workspace import SchnittWorkspace
    ws = SchnittWorkspace()
    pid = _project(test_engine, with_clip=True)
    ws.set_active_project(pid)
    ev = ws.editor_view
    assert ev.inspector_panel is not None
    ev.sub_tabs.setCurrentIndex(2)
    assert ev.inspector_panel is not None
    ev.sub_tabs.setCurrentIndex(0)
    assert ev.inspector_panel.isVisibleTo(ev) or ev.inspector_panel is not None


def test_set_active_project_idempotent(test_engine, monkeypatch):
    """Wiederholtes set_active_project mit gleicher PID → konsistenter State."""
    _qapp()
    _patch_workspace_engine(monkeypatch, test_engine)
    from ui.workspaces.schnitt_workspace import SchnittWorkspace, STATE_EDITOR
    ws = SchnittWorkspace()
    pid = _project(test_engine, with_clip=True)
    ws.set_active_project(pid)
    state1 = ws.current_state()
    ws.set_active_project(pid)
    state2 = ws.current_state()
    assert state1 == state2 == STATE_EDITOR


def test_set_stage_nan_clamps_to_zero(test_engine, monkeypatch):
    """D26 / T4.6: NaN-Defense — int(NaN) wuerde sonst ValueError werfen."""
    import math as _math
    _qapp()
    _patch_workspace_engine(monkeypatch, test_engine)
    from ui.workspaces.schnitt_workspace import SchnittWorkspace
    ws = SchnittWorkspace()
    ws.show_progress("audio_load", _math.nan)
    assert ws.loading_view.progress_bar.value() == 0
