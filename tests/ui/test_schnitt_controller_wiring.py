"""Tier-1 Wiring-Tests fuer SchnittController.

Plan: docs/superpowers/plans/2026-05-09-schnitt-workspace-redesign/
Hardening 2026-05-09 — Tier 1 (Wiring + State-Konflikt-Schutz).

Plan-Abweichung: nutzt `test_engine`-Fixture und monkeypatched `engine`
in `ui.workspaces.schnitt_workspace`, analog zu Phase-02-Tests.
"""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from sqlalchemy.orm import Session
from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


# ---------------------------------------------------------------------------
# B1 — Konstruktor erstellt PacingProfileBinder + initialer apply_profile
# ---------------------------------------------------------------------------

def test_controller_creates_binder_with_pacing_widgets():
    _qapp()
    from ui.workspaces.schnitt_workspace import SchnittWorkspace
    from ui.controllers.schnitt_controller import SchnittController
    from services.ui_binder import PacingProfileBinder
    from services.pacing_profile import PacingProfile

    ws = SchnittWorkspace()
    ctrl = SchnittController(ws)
    assert isinstance(ctrl.profile, PacingProfile)
    assert isinstance(ctrl.binder, PacingProfileBinder)
    tab = ws.editor_view.tab_pacing_anker
    # Initial-Sync: Widget-Werte spiegeln Profile-Defaults
    assert tab.cut_rate_combo.currentIndex() == ctrl.profile.cut_rate_index
    assert tab.reactivity_spin.value() == ctrl.profile.energy_reactivity


# ---------------------------------------------------------------------------
# B7 — Empty-State Preset-Klick verdrahten
# ---------------------------------------------------------------------------

def test_preset_selected_applies_profile_and_emits_request():
    _qapp()
    from ui.workspaces.schnitt_workspace import SchnittWorkspace, STATE_LOADING
    from ui.controllers.schnitt_controller import SchnittController

    ws = SchnittWorkspace()
    ctrl = SchnittController(ws)

    captured = []
    ctrl.request_auto_edit_with_profile.connect(lambda p: captured.append(p))

    ws.empty_view.preset_selected.emit("Techno")

    assert len(captured) == 1
    profile = captured[0]
    # Techno-Preset: cut_rate_index=2, reactivity=70, breakdown=halve
    assert profile.cut_rate_index == 2
    assert profile.energy_reactivity == 70
    assert profile.breakdown == "halve"
    # Binder hat Profil uebernommen
    assert ctrl.profile.style_preset == "Techno"
    assert ctrl.profile.energy_reactivity == 70
    # Loading-State aktiv
    assert ws.current_state() == STATE_LOADING


# ---------------------------------------------------------------------------
# B8 — Empty-State custom_clicked verdrahten
# ---------------------------------------------------------------------------

def test_custom_clicked_emits_open_settings():
    _qapp()
    from ui.workspaces.schnitt_workspace import SchnittWorkspace
    from ui.controllers.schnitt_controller import SchnittController

    ws = SchnittWorkspace()
    ctrl = SchnittController(ws)

    fired = []
    ctrl.request_open_settings.connect(lambda: fired.append(True))

    ws.empty_view.custom_clicked.emit()

    assert fired == [True]


# ---------------------------------------------------------------------------
# B6 — Cancel: bereits in Phase 09 implementiert. Verifizieren.
# ---------------------------------------------------------------------------

def test_cancel_invokes_worker_and_refreshes(test_engine, monkeypatch):
    _qapp()
    import ui.workspaces.schnitt_workspace as ws_mod
    monkeypatch.setattr(ws_mod, "engine", test_engine)

    from ui.workspaces.schnitt_workspace import SchnittWorkspace
    from ui.controllers.schnitt_controller import SchnittController

    ws = SchnittWorkspace()
    ctrl = SchnittController(ws)

    cancelled = []

    class FakeWorker:
        def cancel(self):
            cancelled.append(True)

    ctrl.attach_worker(FakeWorker())
    ws.cancel_requested.emit()
    assert cancelled == [True]
    assert ctrl._current_worker is None


# ---------------------------------------------------------------------------
# D25 — set_active_project_protected ignoriert STATE_LOADING
# ---------------------------------------------------------------------------

def test_set_active_project_protected_skipped_during_loading(test_engine, monkeypatch):
    _qapp()
    import ui.workspaces.schnitt_workspace as ws_mod
    monkeypatch.setattr(ws_mod, "engine", test_engine)

    from ui.workspaces.schnitt_workspace import SchnittWorkspace, STATE_LOADING
    from ui.controllers.schnitt_controller import SchnittController

    ws = SchnittWorkspace()
    ctrl = SchnittController(ws)
    ws.enter_loading()
    assert ws.current_state() == STATE_LOADING

    calls = []
    orig = ws.set_active_project
    def spy(pid):
        calls.append(pid)
        return orig(pid)
    monkeypatch.setattr(ws, "set_active_project", spy)

    ctrl.set_active_project_protected(99)
    assert calls == []  # Loading-Schutz greift
    assert ws.current_state() == STATE_LOADING


def test_set_active_project_protected_runs_when_not_loading(test_engine, monkeypatch):
    _qapp()
    import ui.workspaces.schnitt_workspace as ws_mod
    monkeypatch.setattr(ws_mod, "engine", test_engine)

    from ui.workspaces.schnitt_workspace import SchnittWorkspace, STATE_EMPTY
    from ui.controllers.schnitt_controller import SchnittController
    from database.models import Project

    ws = SchnittWorkspace()
    ctrl = SchnittController(ws)
    assert ws.current_state() == STATE_EMPTY

    with Session(test_engine) as s:
        p = Project(name="protected", path="/tmp/protected")
        s.add(p)
        s.commit()
        pid = p.id

    ctrl.set_active_project_protected(pid)
    # Kein Crash, project_id wurde uebernommen
    assert ws._project_id == pid
