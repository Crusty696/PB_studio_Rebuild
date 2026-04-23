"""SQLite-basierter Vector Database Service fuer semantische Clip-Suche.

Ersetzt LanceDB (haengt auf Windows wegen Tokio/Rust-Runtime-Konflikt).
Speichert 1152-dim SigLIP Embeddings als BLOB in SQLite.
Cosine-Similarity Suche via numpy — performant genug fuer 1000+ Videos.
"""

from __future__ import annotations

import logging
import sqlite3
import threading

from services.timeout_constants import DB_SQLITE_CONNECT_TIMEOUT_SEC
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)

_APP_ROOT = Path(__file__).resolve().parent.parent
DB_DIR = _APP_ROOT / "data" / "vector"
DB_FILE = DB_DIR / "embeddings.db"
EMBEDDING_DIM = 1152

_CREATE_SQL = """
CREATE TABLE IF NOT EXISTS clip_embeddings (
    id INTEGER PRIMARY KEY,
    video_path TEXT NOT NULL,
    scene_index INTEGER NOT NULL,
    scene_start REAL NOT NULL,
    scene_end REAL NOT NULL,
    motion_score REAL DEFAULT 0.0,
    description TEXT DEFAULT '',
    embedding BLOB NOT NULL
)
"""
_INDEX_SQL = "CREATE INDEX IF NOT EXISTS idx_emb_video ON clip_embeddings(video_path)"

# F-030: Singleton
_instance: "VectorDBService | None" = None
_instance_lock = threading.Lock()


class VectorDBService:
    """Verwaltet Embeddings in SQLite fuer semantische Video-Clip-Suche."""

    def __new__(cls, db_path: str | Path | None = None):
        global _instance
        if _instance is None:
            with _instance_lock:
                if _instance is None:
                    obj = super().__new__(cls)
                    obj._initialized = False
                    obj.db_path = Path(db_path) if db_path else DB_FILE
                    obj.db_path.parent.mkdir(parents=True, exist_ok=True)
                    obj._write_lock = threading.Lock()
                    obj._cache_matrix = None
                    obj._cache_metadata = None
                    obj._cache_lock = threading.Lock()
                    obj._init_db()
                    obj._initialized = True
                    _instance = obj
        return _instance

    def __init__(self, db_path: str | Path | None = None):
        pass

    def _invalidate_cache(self):
        with self._cache_lock:
            self._cache_matrix = None
            self._cache_metadata = None

    def _init_db(self):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(_CREATE_SQL)
            conn.execute(_INDEX_SQL)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=DB_SQLITE_CONNECT_TIMEOUT_SEC)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def add_embedding(self, clip_id: int, video_path: str, scene_index: int, 
                      scene_start: float, scene_end: float, embedding: list[float] | np.ndarray,
                      motion_score: float = 0.0, description: str = "") -> None:
        if isinstance(embedding, list):
            embedding = np.array(embedding, dtype=np.float32)
        composite_id = clip_id * 1_000_000 + scene_index
        blob = embedding.astype(np.float32).tobytes()
        with self._write_lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO clip_embeddings (id, video_path, scene_index, scene_start, scene_end, motion_score, description, embedding) VALUES (?,?,?,?,?,?,?,?)",
                    (composite_id, video_path, scene_index, scene_start, scene_end, motion_score, description, blob),
                )
        self._invalidate_cache()

    def add_embeddings_batch(self, clip_id: int, entries: list[dict]) -> None:
        rows = []
        for entry in entries:
            emb = entry.get("embedding")
            if isinstance(emb, list): emb = np.array(emb, dtype=np.float32)
            if not isinstance(emb, np.ndarray): continue
            blob = emb.astype(np.float32).tobytes()
            composite_id = clip_id * 1_000_000 + entry["scene_index"]
            rows.append((composite_id, entry["video_path"], entry["scene_index"], entry["scene_start"], entry["scene_end"], entry.get("motion_score", 0.0), entry.get("description", ""), blob))
        if not rows: return
        with self._write_lock:
            with self._connect() as conn:
                conn.executemany("INSERT OR REPLACE INTO clip_embeddings (id, video_path, scene_index, scene_start, scene_end, motion_score, description, embedding) VALUES (?,?,?,?,?,?,?,?)", rows)
        self._invalidate_cache()

    def search(self, query_embedding: list[float] | np.ndarray, top_k: int = 5, motion_filter: float | None = None) -> list[dict]:
        if isinstance(query_embedding, list): query_embedding = np.array(query_embedding, dtype=np.float32)
        query_norm = query_embedding / (np.linalg.norm(query_embedding) + 1e-8)
        with self._cache_lock:
            if self._cache_matrix is None: self._cache_matrix, self._cache_metadata = self._load_full_data()
            embeddings, metadata = self._cache_matrix, self._cache_metadata
        if embeddings.size == 0: return []
        valid_indices = np.arange(len(metadata))
        if motion_filter is not None:
            valid_indices = [i for i, m in enumerate(metadata) if m["motion_score"] > motion_filter]
            if not valid_indices: return []
            embeddings = embeddings[valid_indices]
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-8
        similarities = (embeddings / norms) @ query_norm
        k = min(top_k, len(similarities))
        top_sub_indices = np.argpartition(-similarities, k - 1)[:k]
        top_sub_indices = top_sub_indices[np.argsort(-similarities[top_sub_indices])]
        results = []
        for idx in top_sub_indices:
            orig_idx = valid_indices[idx]; m = metadata[orig_idx]
            results.append({**m, "_distance": 1.0 - float(similarities[idx])})
        return results

    def _load_full_data(self) -> tuple[np.ndarray, list[dict]]:
        sql = "SELECT id, video_path, scene_index, scene_start, scene_end, motion_score, description, embedding FROM clip_embeddings"
        with self._connect() as conn: rows = conn.execute(sql).fetchall()
        if not rows: return np.empty((0, EMBEDDING_DIM), dtype=np.float32), []
        embeddings = np.vstack([np.frombuffer(row[7], dtype=np.float32) for row in rows])
        metadata = [{"id": r[0], "video_path": r[1], "scene_index": r[2], "scene_start": r[3], "scene_end": r[4], "motion_score": r[5], "description": r[6]} for r in rows]
        return embeddings, metadata

    def get_all_embeddings(self) -> tuple[np.ndarray, list[dict]]:
        sql = "SELECT id, video_path, scene_index, scene_start, scene_end, motion_score, embedding FROM clip_embeddings"
        with self._connect() as conn: rows = conn.execute(sql).fetchall()
        if not rows: return np.empty((0, EMBEDDING_DIM), dtype=np.float32), []
        embeddings = np.vstack([np.frombuffer(row[6], dtype=np.float32) for row in rows])
        metadata = [{"id": r[0], "video_path": r[1], "scene_index": r[2], "scene_start": r[3], "scene_end": r[4], "motion_score": r[5]} for r in rows]
        return embeddings, metadata

    def get_embeddings_by_ids(self, scene_ids: list[int]) -> dict[int, np.ndarray]:
        if not scene_ids: return {}
        placeholders = ",".join(["?"] * len(scene_ids))
        sql = f"SELECT id, embedding FROM clip_embeddings WHERE id IN ({placeholders})"
        results = {}
        with self._connect() as conn:
            rows = conn.execute(sql, scene_ids).fetchall()
            for row in rows:
                results[row[0]] = np.frombuffer(row[1], dtype=np.float32)
        return results

    def get_embeddings_for_clip(self, clip_id: int) -> dict[int, np.ndarray]:
        """Gibt alle Embeddings fuer einen Clip zurueck (via composite id logic)."""
        sql = "SELECT id, embedding FROM clip_embeddings WHERE CAST(id / 1000000 AS INTEGER) = ?"
        results = {}
        with self._connect() as conn:
            rows = conn.execute(sql, (clip_id,)).fetchall()
            for row in rows:
                results[row[0]] = np.frombuffer(row[1], dtype=np.float32)
        return results

    def count(self) -> int:
        with self._connect() as conn: return conn.execute("SELECT COUNT(*) FROM clip_embeddings").fetchone()[0]

    def delete_by_video(self, video_path: str) -> None:
        with self._write_lock:
            with self._connect() as conn: conn.execute("DELETE FROM clip_embeddings WHERE video_path = ?", (video_path,))
            self._invalidate_cache()

    def delete_all(self) -> None:
        with self._write_lock:
            with self._connect() as conn: conn.execute("DELETE FROM clip_embeddings")
            self._invalidate_cache()
