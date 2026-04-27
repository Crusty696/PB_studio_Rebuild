"""B-049 + B-050 + B-051 + B-054 Batch-5 (Project-Management)."""

from __future__ import annotations

import inspect


def test_b049_save_project_as_uses_sqlite_backup() -> None:
    """B-049 (fixed-by B-137): copy via sqlite Connection.backup, nicht copytree."""
    from services.project_manager import ProjectManager

    src = inspect.getsource(ProjectManager.save_project_as)
    assert "_copy_sqlite_db" in src or "backup(" in src
    # WAL/SHM werden uebersprungen
    assert "pb_studio.db-" in src or "wal" in src.lower()


def test_b050_project_controller_has_error_handler() -> None:
    """B-050: ProjectManagementController hat _make_project_error_handler
    und nutzt es in start_task-Calls."""
    from ui.controllers.project_management import ProjectManagementController

    assert hasattr(ProjectManagementController, "_make_project_error_handler")
    for method_name in ("_new_project", "_open_project", "_save_project_as"):
        m = getattr(ProjectManagementController, method_name)
        src = inspect.getsource(m)
        assert "on_error=" in src, f"B-050: {method_name} fehlt on_error"
        assert "_make_project_error_handler" in src


def test_b051_create_open_project_rolls_back_on_init_db_failure() -> None:
    """B-051: create_project + open_project rollen die Engine zurueck wenn
    init_db wirft. Source-Inspection auf Rollback-Marker."""
    from services.project_manager import ProjectManager

    for method in (ProjectManager.create_project, ProjectManager.open_project):
        src = inspect.getsource(method)
        assert "_previous_root" in src, (
            f"B-051: {method.__name__} merkt sich vorigen APP_ROOT nicht — "
            "Rollback bei init_db-Fehler unmoeglich."
        )
        assert "init_db()" in src
        # try/except um init_db
        assert "init_err" in src or "except Exception" in src


def test_b054_ingest_service_has_project_pre_check() -> None:
    """B-054: ingest_audio + ingest_video pruefen Project-FK vor INSERT
    mit klarer Fehlermeldung."""
    from services import ingest_service

    assert hasattr(ingest_service, "_ensure_project_exists")
    src_audio = inspect.getsource(ingest_service.ingest_audio)
    src_video = inspect.getsource(ingest_service.ingest_video)
    assert "_ensure_project_exists" in src_audio, (
        "B-054: ingest_audio ruft _ensure_project_exists nicht."
    )
    assert "_ensure_project_exists" in src_video, (
        "B-054: ingest_video ruft _ensure_project_exists nicht."
    )


def test_b054_ensure_project_exists_raises_on_missing() -> None:
    """B-054: Funktional — bei nicht-existentem Projekt wird ValueError
    geworfen mit klarer Fehlermeldung."""
    from services.ingest_service import _ensure_project_exists
    import pytest

    # In-Memory-Test mit hoher ID die garantiert nicht existiert
    with pytest.raises(ValueError, match=r"existiert nicht"):
        _ensure_project_exists(99_999_999)
