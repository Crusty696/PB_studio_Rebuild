"""E3 (Perf): Brain-Run sammelt Video-IDs per Spalten-Query statt
``get_all_video()`` (Voll-Eager-Load + Status-Reconcile) im GUI-Thread.

Paritaets-Beweis: Die direkte Spalten-Query in
``PBWindow._on_brain_run_requested`` (main.py) muss exakt dieselbe
ID-Liste liefern wie vorher ``[v["id"] for v in get_all_video()]`` —
gleiche Filter (project_id des aktiven Projekts, ``deleted_at IS NULL``,
kein ORDER BY, kein Limit), gleiche Reihenfolge.
"""
import ast
import inspect
import textwrap

from sqlalchemy import event
from sqlalchemy.orm import Session as DBSession

from database.models import Project, VideoClip


def _make_projects_with_clips(test_engine):
    """Synthetische DB: 2 Projekte, Videos mit/ohne deleted_at."""
    from datetime import datetime

    with DBSession(test_engine) as s:
        p1 = Project(name="e3-p1", path="/tmp/e3-p1")
        p2 = Project(name="e3-p2", path="/tmp/e3-p2")
        s.add_all([p1, p2])
        s.flush()
        clips = [
            VideoClip(project_id=p1.id, file_path="/tmp/e3/a.mp4", duration=10.0),
            VideoClip(project_id=p1.id, file_path="/tmp/e3/b.mp4", duration=5.0,
                      deleted_at=datetime(2026, 1, 1)),
            VideoClip(project_id=p1.id, file_path="/tmp/e3/c.mp4", duration=7.0),
            VideoClip(project_id=p2.id, file_path="/tmp/e3/d.mp4", duration=3.0),
            VideoClip(project_id=p2.id, file_path="/tmp/e3/e.mp4", duration=4.0,
                      deleted_at=datetime(2026, 1, 2)),
            VideoClip(project_id=p1.id, file_path="/tmp/e3/f.mp4", duration=9.0),
        ]
        s.add_all(clips)
        s.commit()
        return p1.id, p2.id


def test_e3_column_query_id_parity_with_get_all_video(test_engine):
    """ID-Liste alt (get_all_video) == neu (Spalten-Query), inkl. Reihenfolge."""
    from services.ingest_service import get_all_video

    p1_id, p2_id = _make_projects_with_clips(test_engine)

    for pid in (p1_id, p2_id):
        old_ids = [v["id"] for v in get_all_video(pid)]
        # Exakt die Query aus main.py::_on_brain_run_requested (E3)
        statements: list[str] = []

        def _before(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(test_engine, "before_cursor_execute", _before)
        try:
            with DBSession(test_engine) as session:
                new_ids = [
                    row[0]
                    for row in session.query(VideoClip.id).filter(
                        VideoClip.project_id == pid,
                        VideoClip.deleted_at.is_(None),
                    )
                ]
        finally:
            event.remove(test_engine, "before_cursor_execute", _before)
        assert len(statements) == 1, statements
        assert new_ids == old_ids, (
            f"E3-Paritaet verletzt (project={pid}): "
            f"alt={old_ids} neu={new_ids}"
        )
        # Sanity: deleted Clips sind wirklich rausgefiltert
        with DBSession(test_engine) as session:
            all_ids = {
                row[0] for row in session.query(VideoClip.id).filter(
                    VideoClip.project_id == pid,
                )
            }
        assert set(new_ids) < all_ids


def test_e3_brain_run_slot_uses_column_query_not_get_all_video() -> None:
    """Quelltext-Pin: ``_on_brain_run_requested`` darf ``get_all_video``
    nicht mehr aufrufen (Voll-Load + infer_many_from_db im GUI-Thread)
    und muss stattdessen die Spalten-Query mit identischen Filtern nutzen.
    """
    import importlib

    main_mod = importlib.import_module("main")
    PBWindow = getattr(main_mod, "PBWindow")
    src = inspect.getsource(PBWindow._on_brain_run_requested)

    tree = ast.parse(textwrap.dedent(src))
    called_names = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "get_all_video" not in called_names, (
        "E3: _on_brain_run_requested laedt wieder alle Clips voll — "
        "Freeze-Regression im GUI-Thread."
    )
    assert "VideoClip.id" in src
    assert "_resolve_project_id" in src, (
        "E3: Projekt-Aufloesung muss identisch zu get_all_video bleiben "
        "(_resolve_project_id inkl. Fallback-Semantik)."
    )
    assert "deleted_at" in src, (
        "E3: deleted_at-Filter fehlt — geloeschte Clips wuerden in den "
        "Brain-Run rutschen."
    )
