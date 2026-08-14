"""B-825: Downgrade darf nicht an einem Index auf der gedroppten Spalte scheitern.

``batch_alter_table`` baut eine SQLite-Tabelle beim ``drop_column`` komplett
neu und legt dabei die zuvor reflektierten Indizes wieder an. Liegt ein Index
auf genau der Spalte, die gerade verschwindet, scheitert das mit
``no such column``.

Aufgefallen an ``idx_model_registry_last_used``: der Index kam mit B-819
kanonisch in ``database/models.py`` dazu; seitdem war ``downgrade()`` der
Revision ``a3df65cc10b1`` (M-38) gebrochen und ``test_full_roundtrip_empty_db``
rot. Vor B-819 gab es den Index nicht, deshalb lief es vorher.

Der Roundtrip-Test deckt den Fall mit ab. Diese Datei haelt zusaetzlich die
Ursache fest und prueft, was der Roundtrip nicht prueft: dass der Index nach
dem Downgrade wieder da ist statt stillschweigend verloren zu gehen.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import create_engine, inspect, text

_REVISION = (
    Path(__file__).resolve().parents[2]
    / "database" / "alembic" / "versions"
    / "2026_04_10_a3df65cc10b1_migrate_string_datetime_to_datetime.py"
)


def _load_revision():
    spec = importlib.util.spec_from_file_location("m38_revision", _REVISION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _make_model_registry(conn) -> None:
    """model_registry mit DateTime-Spalten und dem B-819-Index."""
    conn.execute(text(
        "CREATE TABLE model_registry ("
        " id INTEGER PRIMARY KEY,"
        " model_id VARCHAR NOT NULL,"
        " source VARCHAR,"
        " installed_at DATETIME,"
        " last_used_at DATETIME"
        ")"
    ))
    conn.execute(text(
        "CREATE INDEX idx_model_registry_last_used ON model_registry (last_used_at)"
    ))
    conn.execute(text(
        "CREATE INDEX idx_model_registry_source ON model_registry (source)"
    ))
    conn.execute(text(
        "INSERT INTO model_registry (id, model_id, source, installed_at, last_used_at) "
        "VALUES (1, 'gemma3:4b', 'ollama', '2026-01-01 10:00:00', '2026-02-02 11:00:00')"
    ))


def _index_map(conn) -> dict[str, tuple[tuple[str, ...], bool]]:
    return {
        idx["name"]: (tuple(idx["column_names"]), bool(idx["unique"]))
        for idx in inspect(conn).get_indexes("model_registry")
    }


def test_b825_downgrade_survives_index_on_dropped_column():
    """Der eigentliche Fehlerfall: vor dem Fix warf das ``no such column``."""
    module = _load_revision()
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        _make_model_registry(conn)
        module.op = SimpleNamespace(
            get_bind=lambda: conn,
            add_column=lambda table, col: conn.execute(
                text(f"ALTER TABLE {table} ADD COLUMN {col.name} VARCHAR")
            ),
            batch_alter_table=_batch_stub(conn),
        )
        module.downgrade()

        cols = {c["name"] for c in inspect(conn).get_columns("model_registry")}
        assert "last_used_at" in cols
        assert "installed_at" in cols
        assert "last_used_at_new" not in cols


def test_b825_downgrade_restores_the_index():
    """Der Index darf nicht stillschweigend verschwinden."""
    module = _load_revision()
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        _make_model_registry(conn)
        vorher = _index_map(conn)
        module.op = SimpleNamespace(
            get_bind=lambda: conn,
            add_column=lambda table, col: conn.execute(
                text(f"ALTER TABLE {table} ADD COLUMN {col.name} VARCHAR")
            ),
            batch_alter_table=_batch_stub(conn),
        )
        module.downgrade()
        nachher = _index_map(conn)

    assert "idx_model_registry_last_used" in nachher, (
        "Index auf last_used_at ging beim Downgrade verloren"
    )
    assert nachher["idx_model_registry_last_used"] == vorher["idx_model_registry_last_used"]
    assert nachher["idx_model_registry_source"] == vorher["idx_model_registry_source"]


def test_b825_helper_only_touches_matching_indexes():
    """`_drop_indexes_on_column` darf fremde Indizes in Ruhe lassen."""
    module = _load_revision()
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        _make_model_registry(conn)

        entfernt = module._drop_indexes_on_column(conn, "model_registry", "last_used_at")

        namen = {idx["name"] for idx in entfernt}
        assert namen == {"idx_model_registry_last_used"}
        verbleibend = set(_index_map(conn))
        assert "idx_model_registry_last_used" not in verbleibend
        assert "idx_model_registry_source" in verbleibend

        module._recreate_indexes(conn, "model_registry", entfernt)
        assert "idx_model_registry_last_used" in _index_map(conn)


def _batch_stub(conn):
    """Minimaler `batch_alter_table`-Ersatz mit echtem SQLite-Verhalten.

    Bildet nach, was Alembic unter SQLite tut: `drop_column` und
    `alter_column(new_column_name=...)` gehen ueber echtes ALTER TABLE. Das
    genuegt, um den Index-Konflikt zu reproduzieren, ohne den vollen
    Alembic-Migrationskontext aufzubauen.
    """
    from contextlib import contextmanager

    class _Batch:
        def __init__(self, table: str) -> None:
            self.table = table

        def drop_column(self, name: str) -> None:
            conn.execute(text(f"ALTER TABLE {self.table} DROP COLUMN {name}"))

        def alter_column(self, name: str, new_column_name: str = None, **_kw) -> None:
            if new_column_name:
                conn.execute(text(
                    f"ALTER TABLE {self.table} RENAME COLUMN {name} TO {new_column_name}"
                ))

    @contextmanager
    def _factory(table: str, schema=None):
        yield _Batch(table)

    return _factory
