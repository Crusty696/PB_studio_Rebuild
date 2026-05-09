"""Layout + Auto-Save-Tests fuer Sub-Tab RL & Notes (Phase 08 / Task 8.1).

Pattern: test_engine-Fixture aus tests/conftest.py + monkeypatch auf
`services.project_notes_service.engine` (analog test_project_notes_service.py).
Plan-Snippet (08_SUBTAB_RL_NOTES.md) referenziert init_db + DBSession,
das Repo verwendet das Fixture-Pattern.
"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from sqlalchemy.orm import Session
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from database.models import Project
from services.project_notes_service import get_notes
from ui.workspaces.schnitt.tab_rl_notes import SchnittTabRlNotes


def _qapp():
    return QApplication.instance() or QApplication([])


def _patch_engine(monkeypatch, test_engine):
    import services.project_notes_service as svc_mod
    monkeypatch.setattr(svc_mod, "engine", test_engine)


def _project(test_engine, name="rl-notes-test"):
    with Session(test_engine) as s:
        p = Project(name=name, path=f"/tmp/{name}")
        s.add(p)
        s.commit()
        return p.id


def test_widgets_present():
    _qapp()
    t = SchnittTabRlNotes()
    assert t.btn_thumbs_up is not None
    assert t.btn_thumbs_down is not None
    assert t.rl_event_list is not None
    assert t.notes_edit is not None


def test_typing_triggers_autosave_after_debounce(test_engine, monkeypatch):
    _patch_engine(monkeypatch, test_engine)
    app = _qapp()
    pid = _project(test_engine)
    t = SchnittTabRlNotes()
    t.set_active_project(pid)
    t.notes_edit.setPlainText("# Mein Plan")
    # Debounce 1000 ms — verkuerze fuer Test ueber das interne Timer-Objekt
    t._autosave_timer.setInterval(20)
    t._autosave_timer.start()
    # Event-Loop laufen lassen
    QTimer.singleShot(120, app.quit)
    app.exec()
    assert get_notes(pid) == "# Mein Plan"
