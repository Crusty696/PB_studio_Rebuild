"""B-773: Auto-Resume des letzten Projekts beim App-Start.

Befund (Livetest + User-Session 2026-08-07): "Autoload" existierte nie —
die App bootet auf APP_ROOT/pb_studio.db. Ist diese Boot-DB projektlos
(z.B. frischer Worktree), zeigte die App "Kein aktives Projekt" und der
User musste manuell oeffnen. Vertrag:
1. Boot-DB hat Projekt -> kein Auto-Open (Bestandsverhalten unveraendert).
2. Boot-DB leer + gueltiger Recent-Eintrag -> open_project_async(Pfad des
   juengsten Eintrags mit existierender pb_studio.db).
3. Recent leer/ungueltig -> nichts (kein Crash, kein Dialog).
"""
from __future__ import annotations

import pytest

import database
from services.recent_projects import RecentProjectsManager
from ui.controllers.project_management import ProjectManagementController


@pytest.fixture()
def ctrl(monkeypatch):
    # Pytest-Guard gezielt oeffnen — genau das testet der Bulk-Lauf-Schutz:
    # ohne Patch macht auto_resume unter pytest IMMER nichts.
    import ui.controllers.project_management as pm_mod
    monkeypatch.setattr(pm_mod, "_running_under_pytest", lambda: False)
    c = ProjectManagementController.__new__(ProjectManagementController)
    opened: list = []
    c.open_project_async = lambda path, on_error_extra=None: opened.append(path)
    c._opened = opened
    return c


def test_guard_blocks_auto_resume_under_pytest(monkeypatch):
    """Bulk-Lauf-Schutz: unter pytest darf NIE ein echtes Projekt geoeffnet
    werden (Crash im tests/ui-Lauf 2026-08-08)."""
    c = ProjectManagementController.__new__(ProjectManagementController)
    opened: list = []
    c.open_project_async = lambda *a, **k: opened.append(True)
    monkeypatch.setattr(database, "get_active_project_id", lambda: None)
    monkeypatch.setattr(
        RecentProjectsManager, "get_all",
        staticmethod(lambda: [r"C:\echtes\projekt"]),
    )
    c.auto_resume_last_project()  # PYTEST_CURRENT_TEST ist gesetzt
    assert opened == []


def test_existing_project_skips_auto_resume(ctrl, monkeypatch):
    monkeypatch.setattr(database, "get_active_project_id", lambda: 7)
    monkeypatch.setattr(
        RecentProjectsManager, "get_all",
        staticmethod(lambda: [r"C:\irgendwo\projekt"]),
    )
    ctrl.auto_resume_last_project()
    assert ctrl._opened == []


def test_empty_boot_db_resumes_most_recent_valid(ctrl, monkeypatch, tmp_path):
    monkeypatch.setattr(database, "get_active_project_id", lambda: None)
    stale = tmp_path / "geloescht"
    valid = tmp_path / "letztes_projekt"
    valid.mkdir()
    (valid / "pb_studio.db").write_bytes(b"")
    monkeypatch.setattr(
        RecentProjectsManager, "get_all",
        staticmethod(lambda: [str(stale), str(valid)]),
    )
    ctrl.auto_resume_last_project()
    assert [str(p) for p in ctrl._opened] == [str(valid)]


def test_no_valid_recent_does_nothing(ctrl, monkeypatch, tmp_path):
    monkeypatch.setattr(database, "get_active_project_id", lambda: None)
    monkeypatch.setattr(
        RecentProjectsManager, "get_all",
        staticmethod(lambda: [str(tmp_path / "weg")]),
    )
    ctrl.auto_resume_last_project()
    assert ctrl._opened == []
