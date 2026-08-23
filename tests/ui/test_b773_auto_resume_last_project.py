"""B-773: Auto-Resume des letzten Projekts beim App-Start.

Befund (Livetest + User-Session 2026-08-07): "Autoload" existierte nie —
die App bootet auf APP_ROOT/pb_studio.db. Ist diese Boot-DB projektlos
(z.B. frischer Worktree), zeigte die App "Kein aktives Projekt" und der
User musste manuell oeffnen. Vertrag:
1. ProjectManager hat geoeffneten Projektpfad -> kein Auto-Open.
2. Kein geoeffneter Projektpfad + gueltiger Recent-Eintrag ->
   open_project_async(Pfad des juengsten Eintrags mit existierender
   pb_studio.db), unabhaengig von Rows der Boot-DB.
3. Recent leer/ungueltig -> nichts (kein Crash, kein Dialog).
"""
from __future__ import annotations

from types import SimpleNamespace

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
    c.window = SimpleNamespace(
        _project_manager=SimpleNamespace(current_project_path=None),
    )
    opened: list = []
    skip_preblocks: list[bool] = []

    def _open(path, on_error_extra=None, *, skip_preblock=False):
        opened.append(path)
        skip_preblocks.append(skip_preblock)

    c.open_project_async = _open
    c._opened = opened
    c._skip_preblocks = skip_preblocks
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
    ctrl.window = SimpleNamespace(
        _project_manager=SimpleNamespace(current_project_path=r"C:\offen\projekt"),
    )
    monkeypatch.setattr(database, "get_active_project_id", lambda: 7)
    monkeypatch.setattr(
        RecentProjectsManager, "get_all",
        staticmethod(lambda: [r"C:\irgendwo\projekt"]),
    )
    ctrl.auto_resume_last_project()
    assert ctrl._opened == []


def test_boot_db_row_does_not_block_resume_without_open_project(
    ctrl, monkeypatch, tmp_path,
):
    ctrl.window = SimpleNamespace(
        _project_manager=SimpleNamespace(current_project_path=None),
    )
    valid = tmp_path / "isoliertes_recent_projekt"
    valid.mkdir()
    (valid / "pb_studio.db").write_bytes(b"")
    monkeypatch.setattr(database, "get_active_project_id", lambda: 7)
    monkeypatch.setattr(
        RecentProjectsManager, "get_all",
        staticmethod(lambda: [str(valid)]),
    )

    ctrl.auto_resume_last_project()

    assert [str(p) for p in ctrl._opened] == [str(valid)]
    assert ctrl._skip_preblocks == [True]


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
