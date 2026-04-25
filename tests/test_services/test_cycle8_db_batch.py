"""Cycle 8 DB/Migration — RED-Test fuer B-174.

B-175 bleibt status: open (Schema-Migration eigene Story).
"""
from __future__ import annotations

import inspect


def test_b174_fk_migration_pragma_on_in_finally():
    """B-174: _migrate_fk_cascade muss PRAGMA foreign_keys=ON in einem
    finally-Block setzen. Sonst kontaminiert ein Fehler-Pfad den
    SQLAlchemy-Connection-Pool mit FK=OFF — silent FK-Constraint-Bypass."""
    from database import migrations

    src = inspect.getsource(migrations._migrate_fk_cascade)
    # PRAGMA foreign_keys=OFF ist im try-Block (line ~141)
    # PRAGMA foreign_keys=ON MUSS nach einem finally: stehen,
    # nicht im inneren try-Block.
    finally_idx = src.find("finally:")
    fk_on_idx = src.find('PRAGMA foreign_keys=ON')
    assert finally_idx > 0, "_migrate_fk_cascade braucht finally-Block fuer Cleanup."
    assert fk_on_idx > finally_idx, (
        "PRAGMA foreign_keys=ON muss IM finally-Block stehen, "
        "nicht vor dem finally — sonst leakt FK=OFF auf Fehler-Pfad (B-174)."
    )
