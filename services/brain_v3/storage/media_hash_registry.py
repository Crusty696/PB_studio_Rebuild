"""Brain V3 — Media-Hash-Registry (Phase 1 App-Sync).

Persistiert sha256-Hashes von Audio/Video-Dateien direkt beim Import,
bevor Phase 2 Embeddings rechnet. Plan-Amendment 2026-05-05.

Tabelle `media_hashes` liegt als Sibling in embedding_cache.db
(siehe Migration 002_media_hashes.sql).

Public API:
    register(path, media_type) -> RegistrationResult
        Computed Hash, INSERT-OR-IGNORE in DB.
        Liefert ist_neu + hash + size + computed_at.
    lookup(media_hash) -> Optional[HashEntry]
    lookup_by_path(source_path) -> Optional[HashEntry]
    stats() -> dict[str, int]
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from services.brain_v3 import paths
from services.brain_v3.hashing import compute_media_hash
from services.brain_v3.storage.sqlite_init import open_connection
from services.brain_v3.storage.migration_runner import migrate

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = (
    Path(__file__).resolve().parent / "sql_migrations" / "embedding_cache"
)


@dataclass(frozen=True)
class HashEntry:
    media_hash: str
    media_type: str  # 'audio' | 'video'
    source_path: str
    file_size_bytes: int
    computed_at: str


@dataclass(frozen=True)
class RegistrationResult:
    entry: HashEntry
    is_new: bool  # True = neu eingefuegt, False = Hash bereits bekannt


class MediaHashRegistry:
    """Hash-Registry fuer V3-Phase-1-App-Sync."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path) if db_path else paths.embedding_cache_db_path()
        migrate(self.db_path, _MIGRATIONS_DIR)

    def register(self, source_path: Path | str, media_type: str) -> RegistrationResult:
        if media_type not in ("audio", "video"):
            raise ValueError(f"media_type muss 'audio'/'video' sein, war: {media_type}")
        p = Path(source_path).resolve()
        media_hash = compute_media_hash(p)
        size = p.stat().st_size
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        with self._conn() as conn:
            existing = conn.execute(
                "SELECT media_hash, media_type, source_path, file_size_bytes, computed_at "
                "FROM media_hashes WHERE media_hash = ?",
                (media_hash,),
            ).fetchone()
            if existing is not None:
                entry = self._row_to_entry(existing)
                logger.info(
                    "MediaHashRegistry: bekannt hash=%s type=%s",
                    media_hash[:8], entry.media_type,
                )
                return RegistrationResult(entry=entry, is_new=False)

            conn.execute(
                "INSERT INTO media_hashes "
                "(media_hash, media_type, source_path, file_size_bytes, computed_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (media_hash, media_type, str(p), size, now),
            )
            conn.commit()

        entry = HashEntry(
            media_hash=media_hash, media_type=media_type,
            source_path=str(p), file_size_bytes=size, computed_at=now,
        )
        logger.info(
            "MediaHashRegistry: neu hash=%s type=%s size=%d B",
            media_hash[:8], media_type, size,
        )
        return RegistrationResult(entry=entry, is_new=True)

    def lookup(self, media_hash: str) -> Optional[HashEntry]:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT media_hash, media_type, source_path, file_size_bytes, computed_at "
                "FROM media_hashes WHERE media_hash = ?",
                (media_hash,),
            ).fetchone()
        return self._row_to_entry(row) if row else None

    def lookup_by_path(self, source_path: Path | str) -> Optional[HashEntry]:
        p = str(Path(source_path).resolve())
        with self._conn() as conn:
            row = conn.execute(
                "SELECT media_hash, media_type, source_path, file_size_bytes, computed_at "
                "FROM media_hashes WHERE source_path = ?",
                (p,),
            ).fetchone()
        return self._row_to_entry(row) if row else None

    def stats(self) -> dict[str, int]:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM media_hashes").fetchone()[0]
            audio = conn.execute(
                "SELECT COUNT(*) FROM media_hashes WHERE media_type='audio'"
            ).fetchone()[0]
            video = conn.execute(
                "SELECT COUNT(*) FROM media_hashes WHERE media_type='video'"
            ).fetchone()[0]
        return {"total": total, "audio": audio, "video": video}

    def _conn(self) -> sqlite3.Connection:
        return open_connection(self.db_path)

    @staticmethod
    def _row_to_entry(row: tuple) -> HashEntry:
        return HashEntry(
            media_hash=row[0], media_type=row[1], source_path=row[2],
            file_size_bytes=int(row[3] or 0), computed_at=row[4],
        )


_default: Optional[MediaHashRegistry] = None


def get_default_registry() -> MediaHashRegistry:
    """Singleton fuer App-Pfad. Tests sollten eigene Instanz mit db_path bauen."""
    global _default
    if _default is None:
        _default = MediaHashRegistry()
    return _default


def reset_default_registry() -> None:
    """Test-Helper. NICHT aus App-Code aufrufen."""
    global _default
    _default = None
