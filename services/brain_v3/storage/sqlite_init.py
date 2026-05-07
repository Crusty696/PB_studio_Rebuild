"""Brain V3 — SQLite-PRAGMA-Init fuer alle V3-DB-Connections.

Plan-Doc 04: einheitliches PRAGMA-Setup pro Connection — WAL,
NORMAL-sync, 32 MB cache, 256 MB mmap, foreign_keys=ON, busy_timeout=5s.
"""
from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

PRAGMA_INIT: tuple[str, ...] = (
    "PRAGMA journal_mode = WAL",         # persistent, einmal gesetzt bleibt
    "PRAGMA synchronous = NORMAL",       # WAL-sicher + schneller als FULL
    "PRAGMA temp_store = MEMORY",        # temp tables im RAM
    "PRAGMA cache_size = -32000",        # 32 MB pro Connection
    "PRAGMA mmap_size = 268435456",      # 256 MB memory-mapped IO
    "PRAGMA foreign_keys = ON",          # Referential Integrity
    "PRAGMA busy_timeout = 5000",        # 5 s warten bei Lock-Contention
)


def init_connection(conn: sqlite3.Connection) -> None:
    """Wendet alle PRAGMAs auf eine Connection an. Idempotent."""
    for pragma in PRAGMA_INIT:
        try:
            conn.execute(pragma)
        except sqlite3.DatabaseError as exc:
            logger.warning("PRAGMA failed: %s — %s", pragma, exc)


def open_connection(
    db_path: Path | str,
    *,
    load_sqlite_vec: bool = False,
    isolation_level: Optional[str] = None,
) -> sqlite3.Connection:
    """Oeffnet eine SQLite-Connection mit V3-PRAGMA-Defaults.

    Args:
        db_path: Pfad zur DB-Datei. Wird automatisch angelegt wenn missing.
        load_sqlite_vec: True → versucht `sqlite_vec.load(conn)` aufzurufen.
                         Wirft ImportError wenn `sqlite_vec` nicht installiert.
        isolation_level: sqlite3-Default (deferred mode). Mit None → autocommit-Modus.
    """
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), isolation_level=isolation_level)
    init_connection(conn)
    if load_sqlite_vec:
        load_vec_extension(conn)
    return conn


def load_vec_extension(conn: sqlite3.Connection) -> None:
    """Laedt die sqlite-vec Extension. Nur in Embedding-Repository verwenden."""
    try:
        import sqlite_vec  # type: ignore
    except ImportError as exc:
        raise ImportError(
            "sqlite-vec ist nicht installiert. "
            "Im Workspace ausfuehren: "
            "`%PB_PYTHON% -m pip install sqlite-vec` "
            "(oder run_install_brain_v3_phase2_deps.bat doppelklicken)."
        ) from exc

    try:
        conn.enable_load_extension(True)
    except sqlite3.OperationalError as exc:
        raise RuntimeError(
            "sqlite3 wurde ohne enable_load_extension kompiliert. "
            "Auf Windows mit conda-env pb-studio sollte das funktionieren — "
            "falls nicht: User auf py-Build mit Extension-Support hinweisen."
        ) from exc

    sqlite_vec.load(conn)
    conn.enable_load_extension(False)


def checkpoint(conn: sqlite3.Connection, mode: str = "PASSIVE") -> None:
    """Erzwingt WAL-Checkpoint. PASSIVE/RESTART/TRUNCATE."""
    if mode not in ("PASSIVE", "RESTART", "TRUNCATE", "FULL"):
        raise ValueError(f"Ungueltiger Checkpoint-Mode: {mode}")
    conn.execute(f"PRAGMA wal_checkpoint({mode})")
