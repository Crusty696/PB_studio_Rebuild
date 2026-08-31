"""Layout + Auto-Save-Tests fuer Sub-Tab Notizen (frueher "RL & Notes").

B-927: die RL-Haelfte des Tabs ist entfallen (Userentscheidung 2026-08-31),
die Notizen sind unveraendert geblieben.

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
from ui.workspaces.schnitt.tab_notizen import SchnittTabNotizen


def _qapp():
    return QApplication.instance() or QApplication([])


def _patch_engine(monkeypatch, test_engine):
    import services.project_notes_service as svc_mod
    monkeypatch.setattr(svc_mod, "engine", test_engine)


def _project(test_engine, name="notizen-test"):
    with Session(test_engine) as s:
        p = Project(name=name, path=f"/tmp/{name}")
        s.add(p)
        s.commit()
        return p.id


def test_widgets_present():
    _qapp()
    t = SchnittTabNotizen()
    assert t.notes_edit is not None
    assert t.saved_label is not None


def test_rl_widgets_sind_weg():
    """B-927: Daumen-Knoepfe und Ereignisliste duerfen nicht zurueckkehren."""
    _qapp()
    t = SchnittTabNotizen()
    for weg in ("btn_thumbs_up", "btn_thumbs_down", "rl_event_list"):
        assert not hasattr(t, weg), f"{weg} ist wieder da"


def test_typing_triggers_autosave_after_debounce(test_engine, monkeypatch):
    _patch_engine(monkeypatch, test_engine)
    app = _qapp()
    pid = _project(test_engine)
    t = SchnittTabNotizen()
    t.set_active_project(pid)
    t.notes_edit.setPlainText("# Mein Plan")
    # Debounce 1000 ms — verkuerze fuer Test ueber das interne Timer-Objekt
    t._autosave_timer.setInterval(20)
    t._autosave_timer.start()
    # Event-Loop laufen lassen
    QTimer.singleShot(120, app.quit)
    app.exec()
    assert get_notes(pid) == "# Mein Plan"
