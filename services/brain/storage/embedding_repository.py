"""Brain V3 — Repository fuer projekt-spezifische Embeddings (sqlite-vec).

Plan-Doc 04 Schema 4: audio_units (3-Tier) + audio_embeddings (FLOAT[512]) +
video_units (2-Tier) + video_embeddings (FLOAT[768]) in projekt-eigener
embeddings.db unter <project>/brain_v3/embeddings.db.

Einziger Konsument von sqlite_vec.load() im V3-Stack. Alle Reranker-,
SmartSampler-, etc. Konsumenten greifen ueber diese API zu.

Wenn sqlite-vec NICHT installiert: ImportError mit klarer User-Anweisung
(siehe storage.sqlite_init.load_vec_extension).
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from services.brain import paths
from services.brain.storage.sqlite_init import open_connection

logger = logging.getLogger(__name__)

_MIGRATIONS_DIR = (
    Path(__file__).resolve().parent / "sql_migrations" / "embeddings_project"
)

CLAP_DIM = 512
SIGLIP_DIM = 768


# ---------------------------------------------------------------------------
# Datatypes
# ---------------------------------------------------------------------------
@dataclass
class AudioUnit:
    level: str                     # 'mix' | 'section' | 'window'
    media_id: int
    media_hash: str
    start_time: float
    end_time: float
    parent_id: Optional[int] = None
    metadata: dict = field(default_factory=dict)
    id: Optional[int] = None       # gesetzt nach insert


@dataclass
class VideoUnit:
    level: str                     # 'clip' | 'scene' | 'frame'
    media_id: int
    media_hash: str
    start_time: float
    end_time: float
    parent_id: Optional[int] = None
    motion_score: Optional[float] = None
    brightness: Optional[float] = None
    saturation: Optional[float] = None
    color_temp: Optional[float] = None
    metadata: dict = field(default_factory=dict)
    id: Optional[int] = None


@dataclass
class KnnHit:
    unit_id: int
    media_id: int
    distance: float


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------
class EmbeddingRepository:
    """sqlite-vec basiertes Embedding-Storage fuer ein Projekt.

    Usage:
        repo = EmbeddingRepository(project_root=Path('./my_project'))
        unit = repo.add_audio_unit(AudioUnit(level='window', ...))
        repo.add_audio_embedding(unit.id, np.random.randn(512).astype('float32'))
        hits = repo.knn_audio(query_embedding, level='window', k=10)
    """

    def __init__(self, project_root: Path | str):
        self.project_root = Path(project_root)
        self.db_path = paths.project_embeddings_db_path(self.project_root)
        # Migrations brauchen sqlite-vec wegen VIRTUAL TABLE — open mit load_sqlite_vec
        self._init_schema()

    # ------------------------------------------------------------------
    # Schema-Init (Migration)
    # ------------------------------------------------------------------
    def _init_schema(self) -> None:
        # Wir koennen migration_runner nicht direkt nutzen, weil der ohne
        # vec-Extension oeffnet. Stattdessen: Connection mit vec laden und
        # die Migration manuell anwenden.
        conn = open_connection(self.db_path, load_sqlite_vec=True)
        try:
            self._apply_migrations(conn)
        finally:
            conn.close()

    def _apply_migrations(self, conn: sqlite3.Connection) -> None:
        scripts = sorted(_MIGRATIONS_DIR.glob("*.sql"))
        if not scripts:
            return
        current = int(conn.execute("PRAGMA user_version").fetchone()[0] or 0)
        for i, script in enumerate(scripts, start=1):
            if i <= current:
                continue
            sql_text = script.read_text(encoding="utf-8")
            try:
                conn.executescript(
                    f"BEGIN; {sql_text}; PRAGMA user_version = {i}; COMMIT;"
                )
                logger.info("EmbeddingRepository: applied %s -> user_version=%d",
                            script.name, i)
            except sqlite3.Error as exc:
                conn.execute("ROLLBACK")
                raise RuntimeError(
                    f"Migration {script.name} fehlgeschlagen: {exc}"
                ) from exc

    # ------------------------------------------------------------------
    # Audio
    # ------------------------------------------------------------------
    def add_audio_unit(self, unit: AudioUnit) -> AudioUnit:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO audio_units "
                "(parent_id, level, media_id, media_hash, start_time, end_time, metadata_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (unit.parent_id, unit.level, unit.media_id, unit.media_hash,
                 unit.start_time, unit.end_time,
                 json.dumps(unit.metadata) if unit.metadata else None),
            )
            unit.id = int(cur.lastrowid)
            conn.commit()
        return unit

    def add_audio_embedding(self, unit_id: int, embedding: np.ndarray) -> None:
        if embedding.shape != (CLAP_DIM,):
            raise ValueError(f"CLAP-Embedding muss shape ({CLAP_DIM},) haben, war: {embedding.shape}")
        blob = _vec_blob(embedding.astype("float32"))
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO audio_embeddings(rowid, embedding) VALUES (?, ?)",
                (unit_id, blob),
            )
            conn.commit()

    def knn_audio(
        self,
        query: np.ndarray,
        k: int = 10,
        level: Optional[str] = None,
    ) -> list[KnnHit]:
        if query.shape != (CLAP_DIM,):
            raise ValueError(f"CLAP-Query muss shape ({CLAP_DIM},) haben, war: {query.shape}")
        return self._knn(
            table="audio_embeddings",
            unit_table="audio_units",
            query=query.astype("float32"),
            k=k,
            level=level,
        )

    # ------------------------------------------------------------------
    # Video
    # ------------------------------------------------------------------
    def add_video_unit(self, unit: VideoUnit) -> VideoUnit:
        with self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO video_units "
                "(parent_id, level, media_id, media_hash, start_time, end_time, "
                " motion_score, brightness, saturation, color_temp, metadata_json) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (unit.parent_id, unit.level, unit.media_id, unit.media_hash,
                 unit.start_time, unit.end_time,
                 unit.motion_score, unit.brightness, unit.saturation, unit.color_temp,
                 json.dumps(unit.metadata) if unit.metadata else None),
            )
            unit.id = int(cur.lastrowid)
            conn.commit()
        return unit

    def add_video_embedding(self, unit_id: int, embedding: np.ndarray) -> None:
        if embedding.shape != (SIGLIP_DIM,):
            raise ValueError(f"SigLIP-Embedding muss shape ({SIGLIP_DIM},) haben, war: {embedding.shape}")
        blob = _vec_blob(embedding.astype("float32"))
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO video_embeddings(rowid, embedding) VALUES (?, ?)",
                (unit_id, blob),
            )
            conn.commit()

    def knn_video(
        self,
        query: np.ndarray,
        k: int = 10,
        level: Optional[str] = None,
    ) -> list[KnnHit]:
        if query.shape != (SIGLIP_DIM,):
            raise ValueError(f"SigLIP-Query muss shape ({SIGLIP_DIM},) haben, war: {query.shape}")
        return self._knn(
            table="video_embeddings",
            unit_table="video_units",
            query=query.astype("float32"),
            k=k,
            level=level,
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _conn(self) -> sqlite3.Connection:
        return open_connection(self.db_path, load_sqlite_vec=True)

    def _knn(self, table: str, unit_table: str, query: np.ndarray,
             k: int, level: Optional[str]) -> list[KnnHit]:
        blob = _vec_blob(query)
        # sqlite-vec MATCH-Pattern + LIMIT
        sql = (
            f"SELECT u.id, u.media_id, e.distance "  # nosec B608 - interner Identifier (Tabellen-/Spaltenname aus Code-Konstante), kein User-Input; Query-Werte sind parametrisiert
            f"FROM {table} e "
            f"JOIN {unit_table} u ON u.id = e.rowid "
            f"WHERE e.embedding MATCH ? AND k = ? "
        )
        params: list = [blob, k]
        if level is not None:
            sql += "AND u.level = ? "
            params.append(level)
        sql += "ORDER BY e.distance"
        with self._conn() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [KnnHit(unit_id=r[0], media_id=r[1], distance=float(r[2]))
                for r in rows]


# ---------------------------------------------------------------------------
# sqlite-vec Blob-Helper
# ---------------------------------------------------------------------------
def _vec_blob(arr: np.ndarray) -> bytes:
    """sqlite-vec erwartet little-endian float32-Blob."""
    if arr.dtype != np.float32:
        arr = arr.astype(np.float32)
    return arr.tobytes(order="C")
