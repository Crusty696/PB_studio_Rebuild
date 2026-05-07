"""Brain V3 — Lightweight SQL-Migrations via PRAGMA user_version.

Plan-Doc 02 #19: keine Alembic-Dependency. Stattdessen nummerierte
SQL-Skripte und sqlite-eigenes user_version PRAGMA.

V3-Migrations leben in services/brain_v3/storage/sql_migrations/<scope>/
mit Konvention `NNN_<slug>.sql`. Beispiel:
    services/brain_v3/storage/sql_migrations/embedding_cache/001_initial.sql
    services/brain_v3/storage/sql_migrations/state/001_initial.sql

Alembic-Migrations bleiben zustaendig fuer App-Bestand (database/alembic/...) —
NICHT von V3 angefasst.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from services.brain_v3.storage.sqlite_init import init_connection

logger = logging.getLogger(__name__)


def migrate(db_path: Path | str, migrations_dir: Path | str) -> int:
    """Fuehrt alle ausstehenden Migrations atomar aus.

    Args:
        db_path: Ziel-DB-Datei (wird angelegt falls missing).
        migrations_dir: Verzeichnis mit nummerierten *.sql Files
                        (sortiert lexikographisch).

    Returns:
        Hoechste angewandte user_version nach Lauf.
    """
    db_path = Path(db_path)
    migrations_dir = Path(migrations_dir)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    if not migrations_dir.exists():
        raise FileNotFoundError(f"Migrations-Verzeichnis fehlt: {migrations_dir}")

    scripts = sorted(migrations_dir.glob("*.sql"))
    if not scripts:
        logger.info("Keine Migrations in %s — skip.", migrations_dir)
        return 0

    conn = sqlite3.connect(str(db_path))
    try:
        init_connection(conn)
        current_version = _get_user_version(conn)
        logger.info("migrate(%s): aktuelle user_version=%d", db_path.name, current_version)

        for i, script in enumerate(scripts, start=1):
            if i <= current_version:
                continue
            sql_text = script.read_text(encoding="utf-8")
            try:
                conn.executescript(
                    f"BEGIN; {sql_text}; PRAGMA user_version = {i}; COMMIT;"
                )
                logger.info("migrate(%s): applied %s → user_version=%d",
                            db_path.name, script.name, i)
            except sqlite3.Error as exc:
                conn.execute("ROLLBACK")
                raise RuntimeError(
                    f"Migration {script.name} fehlgeschlagen: {exc}"
                ) from exc

        return _get_user_version(conn)
    finally:
        conn.close()


def _get_user_version(conn: sqlite3.Connection) -> int:
    row = conn.execute("PRAGMA user_version").fetchone()
    return int(row[0]) if row else 0
