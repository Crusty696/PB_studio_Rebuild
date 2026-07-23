"""Brain V3 — BrainStore (Plan-Doc 03 Phase 3).

Öffnet die 3 App-globalen V3-DBs unter %APPDATA%\\PB_Studio\\brain_v3\\:
- weights.db        (Beta-Bernoulli α/β)
- patterns.db       (Profil-Korrelationen)
- embedding_cache.db (Hash → Embedding-Lookup, schon Phase 2)

Health-Check + Reset-API. Migrations werden idempotent ausgeführt.
"""
from __future__ import annotations

import logging
import sqlite3
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from services.brain import paths
from services.brain.storage.migration_runner import migrate
from services.brain.storage.sqlite_init import open_connection, checkpoint

logger = logging.getLogger(__name__)

_MIG_BASE = Path(__file__).resolve().parent / "sql_migrations"
_MIG_WEIGHTS = _MIG_BASE / "weights"
_MIG_PATTERNS = _MIG_BASE / "patterns"


@dataclass(frozen=True)
class BrainStoreStats:
    weights_rows: int
    patterns_rows: int
    embedding_cache_rows: int
    weights_db_size_bytes: int
    patterns_db_size_bytes: int
    embedding_cache_db_size_bytes: int


@dataclass(frozen=True)
class BrainStoreHealth:
    """Phase-3 App-Sync Health-Check-Result (06_PHASES.md Z.252-268)."""
    weights_ok: bool
    patterns_ok: bool
    embedding_cache_ok: bool
    migrations_version: int
    disk_space_mb: int
    errors: list[str]


class BrainStore:
    """Container für die drei App-globalen V3-DBs."""

    def __init__(
        self,
        weights_path: Optional[Path] = None,
        patterns_path: Optional[Path] = None,
    ):
        self.weights_path = Path(weights_path) if weights_path else paths.weights_db_path()
        self.patterns_path = Path(patterns_path) if patterns_path else paths.patterns_db_path()
        # Migration ausführen (idempotent)
        self._migrate_with_corruption_recovery(self.weights_path, _MIG_WEIGHTS)
        self._migrate_with_corruption_recovery(self.patterns_path, _MIG_PATTERNS)

    def _migrate_with_corruption_recovery(
        self,
        db_path: Path,
        migrations_dir: Path,
    ) -> int:
        try:
            return migrate(db_path, migrations_dir)
        except Exception as exc:
            if not self._is_recoverable_sqlite_corruption(exc):
                raise
            quarantined = self._quarantine_corrupt_db(db_path)
            logger.warning(
                "BrainStore: %s korrupt, quarantined=%s, recreating empty DB",
                db_path.name,
                quarantined,
            )
            return migrate(db_path, migrations_dir)

    @staticmethod
    def _is_recoverable_sqlite_corruption(exc: Exception) -> bool:
        text = str(exc).lower()
        markers = (
            "file is not a database",
            "database disk image is malformed",
            "malformed database schema",
            "not a database",
        )
        return any(marker in text for marker in markers)

    @staticmethod
    def _quarantine_corrupt_db(db_path: Path) -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        target = db_path.with_name(f"{db_path.name}.corrupt.{ts}")
        if db_path.exists():
            db_path.replace(target)
        for suffix in ("-wal", "-shm"):
            sidecar = Path(str(db_path) + suffix)
            if sidecar.exists():
                sidecar.replace(sidecar.with_name(f"{sidecar.name}.corrupt.{ts}"))
        return target

    # ---- Connection-Helper -----------------------------------------------
    # B-678: Context-Manager mit Transaktion (``with conn:``) UND close.
    # Vorher gaben diese eine rohe Connection zurueck; alle Aufrufer nutzen
    # ``with store.open_weights() as c:`` (intern + brain_v3_service), das nur
    # committete, aber die Connection nie schloss -> Handle-Leck (+ WAL/SHM).
    # Die Umstellung schliesst die externen Callsites transparent mit, weil
    # sie ausschliesslich ``with ... as`` nutzen. Muster wie H-6 / _probe_db.
    @contextmanager
    def open_weights(self):
        conn = open_connection(self.weights_path)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @contextmanager
    def open_patterns(self):
        conn = open_connection(self.patterns_path)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    # ---- Stats ------------------------------------------------------------
    def stats(self) -> BrainStoreStats:
        with self.open_weights() as wc:
            w_rows = wc.execute("SELECT COUNT(*) FROM axis_weights").fetchone()[0]
        with self.open_patterns() as pc:
            p_rows = pc.execute("SELECT COUNT(*) FROM pattern_correlations").fetchone()[0]
        ec_path = paths.embedding_cache_db_path()
        try:
            # B-678: closing() -> Connection wird geschlossen (read-only, kein
            # commit noetig). Vorher blieb sie offen.
            with closing(open_connection(ec_path)) as ec:
                ec_rows = ec.execute("SELECT COUNT(*) FROM media_embedding_index").fetchone()[0]
            ec_size = ec_path.stat().st_size if ec_path.exists() else 0
        except Exception:
            ec_rows = 0
            ec_size = 0
        return BrainStoreStats(
            weights_rows=w_rows, patterns_rows=p_rows, embedding_cache_rows=ec_rows,
            weights_db_size_bytes=self.weights_path.stat().st_size,
            patterns_db_size_bytes=self.patterns_path.stat().st_size,
            embedding_cache_db_size_bytes=ec_size,
        )

    # ---- Reset ------------------------------------------------------------
    def reset(self, also_embedding_cache: bool = False) -> None:
        """Löscht weights + patterns. embedding_cache bleibt per Default
        erhalten (Plan-Doc 05 Reset-Verhalten)."""
        with self.open_weights() as wc:
            wc.execute("DELETE FROM axis_weights")
            wc.commit()
        with self.open_patterns() as pc:
            pc.execute("DELETE FROM pattern_correlations")
            pc.commit()
        if also_embedding_cache:
            ec_path = paths.embedding_cache_db_path()
            # Init EmbeddingCache fall noch nie passiert (Tabelle koennte fehlen)
            from services.brain.storage.embedding_cache import EmbeddingCache
            EmbeddingCache(db_path=ec_path)
            # B-678: closing() -> Connection wird geschlossen; explizites
            # commit unten persistiert das DELETE.
            with closing(open_connection(ec_path)) as ec:
                ec.execute("DELETE FROM media_embedding_index")
                ec.commit()
        logger.info("BrainStore.reset done (embedding_cache also? %s)",
                    also_embedding_cache)

    # ---- Health-Check (Phase-3 App-Sync) ----------------------------------
    def health_check(self) -> BrainStoreHealth:
        """Lesen-only Health-Check der 3 V3-DBs (06_PHASES.md Z.252-268).

        Pruefungen pro DB: Datei vorhanden + lesbar, PRAGMA user_version,
        Sample-SELECT auf Haupttabelle. Plus Disk-Space-Check (>=100 MB
        frei). Exception-frei: alle Fehler in `errors` gesammelt.
        Laufzeit-Budget: <50 ms im Normalfall.
        """
        errors: list[str] = []
        weights_ok = self._probe_db(
            self.weights_path, "axis_weights", errors,
        )
        patterns_ok = self._probe_db(
            self.patterns_path, "pattern_correlations", errors,
        )
        ec_path = paths.embedding_cache_db_path()
        embedding_cache_ok = self._probe_db(
            ec_path, "media_embedding_index", errors,
        )

        # Migrations-Version: hoechste user_version aller 3 DBs (informativ)
        migrations_version = max(
            self._read_user_version(self.weights_path, errors),
            self._read_user_version(self.patterns_path, errors),
            self._read_user_version(ec_path, errors),
        )

        # Disk-Space-Check: 100 MB frei am App-Brain-V3-Volume
        disk_space_mb = 0
        try:
            import shutil
            usage = shutil.disk_usage(str(paths.brain_v3_app_dir(create=True)))
            disk_space_mb = int(usage.free / (1024 * 1024))
            if disk_space_mb < 100:
                errors.append(
                    f"Disk-Space niedrig: nur {disk_space_mb} MB frei (<100 MB)"
                )
        except Exception as exc:
            errors.append(f"Disk-Space-Check fehlgeschlagen: {exc}")

        return BrainStoreHealth(
            weights_ok=weights_ok,
            patterns_ok=patterns_ok,
            embedding_cache_ok=embedding_cache_ok,
            migrations_version=migrations_version,
            disk_space_mb=disk_space_mb,
            errors=errors,
        )

    @staticmethod
    def _probe_db(db_path: Path, table_name: str, errors: list[str]) -> bool:
        if not db_path.exists():
            errors.append(f"DB fehlt: {db_path.name}")
            return False
        try:
            conn = sqlite3.connect(str(db_path))
            try:
                conn.execute(f"SELECT 1 FROM {table_name} LIMIT 1").fetchone()  # nosec B608 - interner Identifier (Tabellen-/Spaltenname aus Code-Konstante), kein User-Input; Query-Werte sind parametrisiert
                return True
            finally:
                conn.close()
        except sqlite3.Error as exc:
            errors.append(f"DB unlesbar ({db_path.name}): {exc}")
            return False

    @staticmethod
    def _read_user_version(db_path: Path, errors: list[str]) -> int:
        if not db_path.exists():
            return 0
        try:
            conn = sqlite3.connect(str(db_path))
            try:
                row = conn.execute("PRAGMA user_version").fetchone()
                return int(row[0]) if row else 0
            finally:
                conn.close()
        except sqlite3.Error as exc:
            errors.append(f"user_version-Read ({db_path.name}): {exc}")
            return 0

    # ---- Wartung ----------------------------------------------------------
    def checkpoint_all(self, mode: str = "TRUNCATE") -> None:
        with self.open_weights() as wc:
            checkpoint(wc, mode)
        with self.open_patterns() as pc:
            checkpoint(pc, mode)
