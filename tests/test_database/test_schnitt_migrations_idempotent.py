"""SCHNITT-Redesign Task 1.4: Migrations-Idempotenz.

Verifiziert dass ``_run_legacy_migrations()`` zweimal hintereinander
ohne Fehler laeuft. Die drei in Task 1.1/1.2/1.3 hinzugefuegten Bloecke
(``timeline_entries.locked``, ``timeline_snapshots``, ``project_notes``)
muessen Existence-Checks vor ALTER/CREATE durchfuehren — sonst crashed
``init_db()`` beim zweiten App-Start auf einer schon migrierten DB.

Die Migration-Funktion liest ``engine`` und ``get_raw_engine`` modul-
weit aus ``database.session``. Die ``test_engine``-Fixture aus
``conftest.py`` reicht nicht aus, weil sie ``database.engine`` patcht
aber nicht die in ``database.migrations`` bereits importierten Symbole.
Daher patchen wir hier explizit ``database.migrations.engine`` und
``database.migrations.get_raw_engine`` auf eine frische In-Memory-
Engine.
"""
from sqlalchemy import create_engine, event, inspect

from database import migrations as migrations_mod
from database.models import Base


def _make_inmemory_engine():
    eng = create_engine(
        "sqlite:///:memory:",
        echo=False,
        connect_args={"check_same_thread": False},
    )

    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    return eng


def test_legacy_migrations_run_twice_does_not_raise(monkeypatch):
    eng = _make_inmemory_engine()
    Base.metadata.create_all(eng)

    # ``_run_legacy_migrations`` greift auf modul-globale Symbole zu
    # (``engine``, ``get_raw_engine``) — die wurden bei Modul-Load
    # aus ``database.session`` importiert. Wir patchen sie direkt
    # im migrations-Modul, damit die Funktion gegen die In-Memory-DB
    # arbeitet statt gegen die echte ``pb_studio.db``.
    monkeypatch.setattr(migrations_mod, "engine", eng)
    monkeypatch.setattr(migrations_mod, "get_raw_engine", lambda: eng)

    # Lauf 1 — auf einer frisch via ``Base.metadata.create_all`` erzeugten
    # DB sollten alle Existence-Checks ``True`` zurueckgeben (Spalten und
    # Tabellen sind schon da) und nichts ALTERN/CREATEN.
    migrations_mod._run_legacy_migrations()

    # Lauf 2 — muss ebenso ohne Exception durchlaufen.
    migrations_mod._run_legacy_migrations()

    # Schema-Konsistenz nach 2 Laeufen verifizieren.
    insp = inspect(eng)
    te_cols = {c["name"] for c in insp.get_columns("timeline_entries")}
    assert "locked" in te_cols, "locked-Spalte fehlt nach Migration"

    tables = set(insp.get_table_names())
    assert "timeline_snapshots" in tables, "timeline_snapshots-Tabelle fehlt"
    assert "project_notes" in tables, "project_notes-Tabelle fehlt"
