"""B-138 regression test: OpenProjectDialog must validate SQLite magic.

Cycle-3 tester flagged: ``_check_path`` only verified file existence.
A 0-byte or text file named pb_studio.db produced "found" but the
subsequent open_project crashed with "file is not a database".
"""

from __future__ import annotations

import inspect

from ui.dialogs.project_dialog import OpenProjectDialog


def test_check_path_validates_sqlite_magic_header() -> None:
    src = inspect.getsource(OpenProjectDialog._check_path)
    # Must read the file and check for the SQLite-3 magic header.
    has_magic_check = (
        b"SQLite format 3" in src.encode("utf-8")
        or "SQLite format 3" in src
    )
    assert has_magic_check, (
        "BUG-138 regression: _check_path still only checks .exists() "
        "without verifying the SQLite magic header. Read the first "
        "16 bytes and assert they start with b'SQLite format 3\\x00'."
    )
