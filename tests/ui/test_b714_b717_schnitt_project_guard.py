"""B-714 / B-717 — Projekt-Guards im SchnittController.

B-714: Ein Worker-Ergebnis (done/failed) wurde ohne Projekt-Generations-Guard
angewandt. Wechselt der User waehrend des Laufs das Projekt, lief
``refresh_state_from_db()`` mit der alten ``workspace._project_id`` gegen die
neue Projekt-DB — das Ergebnis landete im falschen Projekt. Vorbild fuer den
Guard: ``expected_db_url`` in ``services/video_analysis_service.py``.

B-717: Der Cockpit-Sprung nach SCHNITT pusht das aktive Projekt doppelt
(``nav_bar.set_workspace(2)`` -> _on_workspace_changed -> Push, danach
``_handle_cockpit_action`` -> Push). Jeder Push kostet eine synchrone
TimelineEntry-COUNT-Query im GUI-Thread.
"""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication


def _qapp():
    return QApplication.instance() or QApplication([])


class _FakeEngine:
    """Minimaler Engine-Stand-in — nur ``url`` wird fuer das Token gelesen."""

    def __init__(self, url: str):
        self.url = url


def _make_ctrl(test_engine, monkeypatch):
    _qapp()
    import ui.workspaces.schnitt_workspace as ws_mod
    monkeypatch.setattr(ws_mod, "engine", test_engine)
    from ui.workspaces.schnitt_workspace import SchnittWorkspace
    from ui.controllers.schnitt_controller import SchnittController

    ws = SchnittWorkspace()
    return ws, SchnittController(ws)


# ---------------------------------------------------------------------------
# B-714
# ---------------------------------------------------------------------------

def test_b714_done_after_project_switch_is_not_applied(test_engine, monkeypatch):
    """RED ohne Guard: done() nach Projektwechsel ruft refresh_state_from_db()
    und wendet damit das Ergebnis auf dem falschen Projekt an."""
    ws, ctrl = _make_ctrl(test_engine, monkeypatch)
    import database
    import database.session as db_session

    applied: list[str] = []
    monkeypatch.setattr(ws, "refresh_state_from_db", lambda: applied.append("refresh"))
    resynced: list[object] = []
    monkeypatch.setattr(ws, "set_active_project", lambda pid: resynced.append(pid))
    monkeypatch.setattr(database, "get_active_project_id", lambda: 42)

    # Projekt A aktiv, Worker startet
    monkeypatch.setattr(db_session, "engine", _FakeEngine("sqlite:///A/pb.db"))

    class _W:
        pass

    worker = _W()
    ctrl.attach_worker(worker)
    assert ctrl._worker_project_token is not None

    # User wechselt mid-run auf Projekt B (EngineProxy.swap-Aequivalent)
    monkeypatch.setattr(db_session, "engine", _FakeEngine("sqlite:///B/pb.db"))

    ctrl._on_done()

    assert applied == [], "Ergebnis aus Projekt A darf in Projekt B nicht angewandt werden"
    # Statt im LOADING-State haengen zu bleiben: Resync auf das aktive Projekt
    assert resynced == [42]
    assert ctrl._current_worker is None


def test_b714_failed_after_project_switch_is_not_applied(test_engine, monkeypatch):
    """Gleicher Guard im failed()-Pfad."""
    ws, ctrl = _make_ctrl(test_engine, monkeypatch)
    import database
    import database.session as db_session

    applied: list[str] = []
    monkeypatch.setattr(ws, "refresh_state_from_db", lambda: applied.append("refresh"))
    monkeypatch.setattr(ws, "set_active_project", lambda pid: None)
    monkeypatch.setattr(database, "get_active_project_id", lambda: 7)

    monkeypatch.setattr(db_session, "engine", _FakeEngine("sqlite:///A/pb.db"))

    class _W:
        pass

    ctrl.attach_worker(_W())
    monkeypatch.setattr(db_session, "engine", _FakeEngine("sqlite:///B/pb.db"))

    ctrl._on_failed()

    assert applied == []


def test_b714_done_in_same_project_is_still_applied(test_engine, monkeypatch):
    """Positiv-Kontrolle: ohne Projektwechsel bleibt der normale Pfad aktiv."""
    ws, ctrl = _make_ctrl(test_engine, monkeypatch)
    import database.session as db_session

    applied: list[str] = []
    monkeypatch.setattr(ws, "refresh_state_from_db", lambda: applied.append("refresh"))
    monkeypatch.setattr(db_session, "engine", _FakeEngine("sqlite:///A/pb.db"))

    class _W:
        pass

    ctrl.attach_worker(_W())
    ctrl._on_done()

    assert applied == ["refresh"]
    assert ctrl._current_worker is None


# ---------------------------------------------------------------------------
# B-717
# ---------------------------------------------------------------------------

def test_b717_double_push_in_same_turn_hits_db_once(test_engine, monkeypatch):
    """RED ohne Fix: der doppelte Cockpit-Push loest zwei identische
    set_active_project-Durchlaeufe (je eine COUNT-Query) aus."""
    ws, ctrl = _make_ctrl(test_engine, monkeypatch)

    calls: list[object] = []
    monkeypatch.setattr(ws, "set_active_project", lambda pid: calls.append(pid))

    # Cockpit: nav_bar.set_workspace(2) -> Push, danach direkter Push
    ctrl.set_active_project_protected(5)
    ctrl.set_active_project_protected(5)

    assert calls == [5]


def test_b717_dedup_is_only_one_event_turn(test_engine, monkeypatch):
    """Kein Dauer-Dedup: nach dem Event-Turn wird wieder frisch gelesen
    (sonst blieben EMPTY/EDITOR-Wechsel stale)."""
    ws, ctrl = _make_ctrl(test_engine, monkeypatch)

    calls: list[object] = []
    monkeypatch.setattr(ws, "set_active_project", lambda pid: calls.append(pid))

    ctrl.set_active_project_protected(5)
    ctrl.set_active_project_protected(5)
    QApplication.processEvents()
    ctrl.set_active_project_protected(5)

    assert calls == [5, 5]


def test_b717_different_project_is_never_deduped(test_engine, monkeypatch):
    """Anderer Projekt-Push im selben Turn muss durchgehen."""
    ws, ctrl = _make_ctrl(test_engine, monkeypatch)

    calls: list[object] = []
    monkeypatch.setattr(ws, "set_active_project", lambda pid: calls.append(pid))

    ctrl.set_active_project_protected(5)
    ctrl.set_active_project_protected(6)

    assert calls == [5, 6]


def test_b717_dedup_does_not_break_loading_guard(test_engine, monkeypatch):
    """D25-Regression: waehrend STATE_LOADING bleibt jeder Push blockiert."""
    ws, ctrl = _make_ctrl(test_engine, monkeypatch)
    from ui.workspaces.schnitt_workspace import STATE_LOADING

    ws.enter_loading()
    assert ws.current_state() == STATE_LOADING

    calls: list[object] = []
    monkeypatch.setattr(ws, "set_active_project", lambda pid: calls.append(pid))
    ctrl.set_active_project_protected(5)

    assert calls == []


def test_b714_token_changes_with_engine_url(monkeypatch):
    """Das Token muss sich mit der Engine-URL aendern (Projektordner-Wechsel)."""
    import database.session as db_session
    from ui.controllers.schnitt_controller import _current_project_token

    monkeypatch.setattr(db_session, "engine", _FakeEngine("sqlite:///A/pb.db"))
    token_a = _current_project_token()
    monkeypatch.setattr(db_session, "engine", _FakeEngine("sqlite:///B/pb.db"))
    token_b = _current_project_token()

    assert token_a is not None and token_b is not None
    assert token_a != token_b


def test_b714_token_none_disables_guard(test_engine, monkeypatch):
    """Fail-open wie expected_db_url=None: ohne Token kein Verwerfen."""
    ws, ctrl = _make_ctrl(test_engine, monkeypatch)
    import ui.controllers.schnitt_controller as ctrl_mod

    applied: list[str] = []
    monkeypatch.setattr(ws, "refresh_state_from_db", lambda: applied.append("refresh"))
    monkeypatch.setattr(ctrl_mod, "_current_project_token", lambda: None)

    class _W:
        pass

    ctrl.attach_worker(_W())
    ctrl._on_done()

    assert applied == ["refresh"]
