"""B-691: Der FK-CASCADE-Migrations-Backup muss WAL-sicher sein.

``shutil.copy2`` kopiert nur die Haupt-Datei. Bei aktivem WAL liegen
committete, noch nicht gecheckpointete Zeilen im ``-wal``-Sidecar -> ein
File-Copy verliert sie still. Der Fix nutzt ``sqlite3.Connection.backup()``
(B-498-Muster). Dieser Test belegt, dass WAL-residente Daten im Backup ankommen
und dass ein naiver copy2 sie verliert.
"""
import shutil
import sqlite3
from pathlib import Path

from database.migrations import _wal_safe_db_copy


def _open_wal_db_with_uncheckpointed_row(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE t (x INTEGER)")
    conn.execute("INSERT INTO t VALUES (42)")
    conn.commit()  # committed -> liegt im -wal, solange keine Checkpoint/Close
    # Connection OFFEN lassen: verhindert Checkpoint-on-last-close.
    return conn


def _read_x(db: Path) -> int | None:
    ro = sqlite3.connect(f"{db.resolve().as_uri()}?mode=ro", uri=True)
    try:
        row = ro.execute("SELECT x FROM t").fetchone()
        return row[0] if row else None
    finally:
        ro.close()


def test_wal_safe_copy_preserves_uncheckpointed_row(tmp_path):
    src = tmp_path / "pb_studio.db"
    conn = _open_wal_db_with_uncheckpointed_row(src)
    try:
        backup = tmp_path / "backup.db"
        _wal_safe_db_copy(src, backup)
        assert _read_x(backup) == 42, "WAL-residente Zeile fehlt im WAL-sicheren Backup"
    finally:
        conn.close()


def test_naive_copy2_would_lose_the_row(tmp_path):
    """Kontroll-Assertion: dokumentiert die Regression, die B-691 behebt.

    Solange die Zeile nur im -wal liegt, enthaelt eine reine Kopie der
    Haupt-Datei sie NICHT (Tabelle existiert dort noch gar nicht).
    """
    src = tmp_path / "pb_studio.db"
    conn = _open_wal_db_with_uncheckpointed_row(src)
    try:
        naive = tmp_path / "naive.db"
        shutil.copy2(src, naive)  # nur Haupt-Datei, ohne -wal
        ro = sqlite3.connect(f"{naive.resolve().as_uri()}?mode=ro", uri=True)
        try:
            tables = ro.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='t'"
            ).fetchall()
        finally:
            ro.close()
        assert tables == [], "Erwartet: naives copy2 verliert die WAL-residente Tabelle"
    finally:
        conn.close()
