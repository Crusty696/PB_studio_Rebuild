"""B-137 regression test: save_project_as must use SQLite-safe hot-copy.

Cycle-3 tester flagged: shutil.copytree on an active SQLite DB risks
WAL/SHM-mid-write inconsistency in the destination project.

Fix: use ``sqlite3.Connection.backup()`` API for pb_studio.db, then
shutil for the rest of the project tree (non-DB storage).
"""

from __future__ import annotations

import inspect

from services.project_manager import ProjectManager


def test_save_project_as_uses_sqlite_backup_or_dispose() -> None:
    """``save_project_as`` source must either:
    - use ``sqlite3.Connection.backup()`` for pb_studio.db, OR
    - explicitly call ``engine.dispose()`` before shutil.copytree
      (so no open WAL/SHM during copy).
    """
    src = inspect.getsource(ProjectManager.save_project_as)

    has_backup = ".backup(" in src or "Connection.backup" in src
    has_dispose = ".dispose()" in src

    assert has_backup or has_dispose, (
        "BUG-137 regression: save_project_as still uses shutil.copytree "
        "on an open SQLite DB without backup() API or engine.dispose(). "
        "Risk: corrupted target project from WAL/SHM mid-write inconsistency."
    )
