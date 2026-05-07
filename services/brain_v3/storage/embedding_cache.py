"""Brain V3 — Hash-basierter Embedding-Cache (Plan-Doc 04 Schema 3).

Persistierung in `%APPDATA%\\PB_Studio\\brain_v3\\embedding_cache.db` plus
`.npy` Embedding-Files in `%APPDATA%\\PB_Studio\\brain_v3\\embeddings\\`.

Cache-Hit-Rate ≥95% bei Re-Imports ist Phase-2-DoD-Ziel (Plan-Doc 06).

Einziger Konsument von sqlite3.connect() fuer den Cache. Kein direkter
sqlite3-Zugriff aus audio_embedder/video_embedder.
"""
from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

import numpy as np

from services.brain_v3 import paths
from services.brain_v3.storage.sqlite_init import open_connection
from services.brain_v3.storage.migration_runner import migrate

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = (
    Path(__file__).resolve().parent / "sql_migrations" / "embedding_cache"
)


@dataclass(frozen=True)
class CacheEntry:
    media_hash: str
    media_type: str  # 'audio' | 'video'
    embedding_path: Path
    model_name: str
    model_version: str
    computed_at: str
    file_size_bytes: int

    def load_embedding(self) -> np.ndarray:
        if not self.embedding_path.exists():
            raise FileNotFoundError(
                f"Embedding-File fehlt fuer hash={self.media_hash}: {self.embedding_path}"
            )
        return np.load(self.embedding_path)


class EmbeddingCache:
    """Index-DB + .npy-File-Storage fuer projekt-uebergreifenden Embedding-Cache."""

    def __init__(
        self,
        db_path: Optional[Path] = None,
        embeddings_dir: Optional[Path] = None,
    ):
        self.db_path = Path(db_path) if db_path else paths.embedding_cache_db_path()
        self.embeddings_dir = (
            Path(embeddings_dir) if embeddings_dir else paths.brain_v3_app_embeddings_dir()
        )
        # Erstmals: Migrate
        migrate(self.db_path, _MIGRATIONS_DIR)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def lookup(
        self,
        media_hash: str,
        model_name: str,
        model_version: str,
    ) -> Optional[CacheEntry]:
        """Liefert Cache-Entry wenn Hash + Model-Version exakt passen, sonst None."""
        with self._conn() as conn:
            row = conn.execute(
                "SELECT media_hash, media_type, embedding_path, model_name, "
                "model_version, computed_at, file_size_bytes "
                "FROM media_embedding_index "
                "WHERE media_hash = ? AND model_name = ? AND model_version = ?",
                (media_hash, model_name, model_version),
            ).fetchone()
        if row is None:
            return None
        return self._row_to_entry(row)

    def store(
        self,
        media_hash: str,
        media_type: str,
        embedding: np.ndarray,
        model_name: str,
        model_version: str,
    ) -> CacheEntry:
        """Speichert Embedding als .npy + Index-Eintrag. Idempotent (overwrite)."""
        if media_type not in ("audio", "video"):
            raise ValueError(f"media_type muss 'audio'/'video' sein, war: {media_type}")
        if not isinstance(embedding, np.ndarray):
            raise TypeError(f"embedding muss numpy.ndarray sein, war: {type(embedding)}")
        if media_hash and (len(media_hash) != 64):
            raise ValueError(f"media_hash muss 64 hex chars sein, war len={len(media_hash)}")

        emb_path = self._path_for(media_hash, media_type, model_name, model_version)
        emb_path.parent.mkdir(parents=True, exist_ok=True)
        np.save(emb_path, embedding)
        size = emb_path.stat().st_size
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")

        with self._conn() as conn:
            conn.execute(
                "INSERT INTO media_embedding_index "
                "(media_hash, media_type, embedding_path, model_name, model_version, "
                " computed_at, file_size_bytes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(media_hash) DO UPDATE SET "
                "  media_type=excluded.media_type, "
                "  embedding_path=excluded.embedding_path, "
                "  model_name=excluded.model_name, "
                "  model_version=excluded.model_version, "
                "  computed_at=excluded.computed_at, "
                "  file_size_bytes=excluded.file_size_bytes",
                (media_hash, media_type, str(emb_path), model_name, model_version,
                 now, size),
            )
            conn.commit()

        logger.info("EmbeddingCache.store: hash=%s model=%s/%s size=%d B",
                    media_hash[:8], model_name, model_version, size)
        return CacheEntry(
            media_hash=media_hash, media_type=media_type, embedding_path=emb_path,
            model_name=model_name, model_version=model_version,
            computed_at=now, file_size_bytes=size,
        )

    def delete(self, media_hash: str) -> bool:
        """Entfernt Entry + .npy-File. Returns True wenn etwas geloescht wurde."""
        entry = None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT media_hash, media_type, embedding_path, model_name, "
                "model_version, computed_at, file_size_bytes "
                "FROM media_embedding_index WHERE media_hash = ?",
                (media_hash,),
            ).fetchone()
            if row is None:
                return False
            entry = self._row_to_entry(row)
            conn.execute("DELETE FROM media_embedding_index WHERE media_hash = ?",
                         (media_hash,))
            conn.commit()
        try:
            entry.embedding_path.unlink(missing_ok=True)
        except Exception as exc:
            logger.warning("EmbeddingCache.delete: file unlink failed: %s", exc)
        return True

    def stats(self) -> dict[str, int]:
        with self._conn() as conn:
            total = conn.execute("SELECT COUNT(*) FROM media_embedding_index").fetchone()[0]
            audio = conn.execute(
                "SELECT COUNT(*) FROM media_embedding_index WHERE media_type='audio'"
            ).fetchone()[0]
            video = conn.execute(
                "SELECT COUNT(*) FROM media_embedding_index WHERE media_type='video'"
            ).fetchone()[0]
        return {"total": total, "audio": audio, "video": video}

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _conn(self) -> sqlite3.Connection:
        # Pro Aufruf neue Connection (sqlite3 ist nicht thread-safe shared) —
        # WAL macht das billig.
        return open_connection(self.db_path)

    def _path_for(self, media_hash: str, media_type: str,
                  model_name: str, model_version: str) -> Path:
        # Nested-Pfad damit ein Verzeichnis nicht 100k+ Files haelt
        # Beispiel: <embeddings_dir>/audio/laion__larger_clap_music__1.0/ab/abcdef…01.npy
        safe_model = model_name.replace("/", "__").replace("\\", "__")
        safe_ver = model_version.replace("/", "_")
        prefix = (media_hash[:2] or "00")
        return (
            self.embeddings_dir
            / media_type
            / f"{safe_model}__{safe_ver}"
            / prefix
            / f"{media_hash}.npy"
        )

    @staticmethod
    def _row_to_entry(row: tuple) -> CacheEntry:
        return CacheEntry(
            media_hash=row[0], media_type=row[1],
            embedding_path=Path(row[2]),
            model_name=row[3], model_version=row[4],
            computed_at=row[5], file_size_bytes=int(row[6] or 0),
        )
