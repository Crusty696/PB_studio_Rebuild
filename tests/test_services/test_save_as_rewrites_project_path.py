"""Save-As muss ``projects.path`` in der Kopie auf den neuen Ordner ziehen.

Befund (Audit 2026-07-27, Bereich db-persistenz, bestaetigt):
``save_project_as`` kopiert die DB und oeffnet die Kopie; ``Project.path`` wird
ausser in ``create_project`` nirgends geschrieben. Die Kopie trug damit weiter
den Pfad des Originals. ``record_manifest_job`` dedupt seine Eintraege im
globalen by_sha-Manifest ueber (normalisierter ``project_path``, ``step_id``) —
Original und Kopie liefern denselben Key und ueberschreiben sich gegenseitig.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from services.project_manager import ProjectManager


def _make_db(db_file: Path, project_path: str) -> None:
    db_file.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(db_file)) as conn:
        conn.execute(
            "CREATE TABLE projects (id INTEGER PRIMARY KEY, name TEXT, "
            "path TEXT, resolution TEXT, fps REAL)"
        )
        conn.execute(
            "INSERT INTO projects (name, path, resolution, fps) VALUES (?,?,?,?)",
            ("P", project_path, "1920x1080", 30.0),
        )


def _stored_path(db_file: Path) -> str:
    with sqlite3.connect(str(db_file)) as conn:
        return conn.execute("SELECT path FROM projects LIMIT 1").fetchone()[0]


def test_rewrite_project_path_updates_copy(tmp_path: Path) -> None:
    old_root = tmp_path / "orig"
    new_root = tmp_path / "kopie"
    db_file = new_root / "pb_studio.db"
    _make_db(db_file, str(old_root))

    ProjectManager._rewrite_project_path(db_file, old_root=old_root, new_root=new_root)

    assert _stored_path(db_file) == str(new_root)


def test_rewrite_project_path_falls_back_on_single_row(tmp_path: Path) -> None:
    """Abweichende Schreibweise im gespeicherten Pfad: per-Projekt-DB hat genau
    eine Zeile, die Zuordnung bleibt eindeutig."""
    new_root = tmp_path / "kopie"
    db_file = new_root / "pb_studio.db"
    _make_db(db_file, "C:\\ANDERS\\geschrieben")

    ProjectManager._rewrite_project_path(
        db_file, old_root=tmp_path / "orig", new_root=new_root
    )

    assert _stored_path(db_file) == str(new_root)


def test_save_project_as_rewrites_path_before_open(tmp_path: Path, monkeypatch) -> None:
    """Verdrahtung: der Rewrite muss im Save-As-Pfad tatsaechlich passieren —
    und VOR dem Oeffnen der Kopie."""
    source = tmp_path / "orig"
    source.mkdir()
    _make_db(source / "pb_studio.db", str(source))
    target = tmp_path / "kopie"

    import database.session as _session

    monkeypatch.setattr(_session, "APP_ROOT", source, raising=False)
    monkeypatch.setattr(ProjectManager, "_wait_for_tasks_idle", staticmethod(
        lambda *a, **kw: True
    ))

    seen: dict[str, str] = {}

    def _fake_open(self, path, task_id=None):
        seen["path_at_open"] = _stored_path(Path(path) / "pb_studio.db")
        return {}

    monkeypatch.setattr(ProjectManager, "open_project", _fake_open)

    mgr = ProjectManager()
    mgr.save_project_as(target)

    assert seen["path_at_open"] == str(target)
