"""SQLite-basierter Vector Database Service fuer semantische Clip-Suche.

Ersetzt LanceDB (haengt auf Windows wegen Tokio/Rust-Runtime-Konflikt).
Speichert 1152-dim SigLIP Embeddings als BLOB in SQLite.
Cosine-Similarity Suche via numpy — performant genug fuer 1000+ Videos.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any

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


class VectorDBService:
    """Verwaltet Embeddings in SQLite fuer semantische Video-Clip-Suche.

    Ersetzt LanceDB komplett. Cosine-Similarity via numpy.
    Thread-safe via Write-Lock.
    """

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else DB_FILE
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(_CREATE_SQL)
            conn.execute(_INDEX_SQL)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(str(self.db_path), timeout=30)

    def add_embedding(
        self,
        clip_id: int,
        video_path: str,
        scene_index: int,
        scene_start: float,
        scene_end: float,
        embedding: list[float] | np.ndarray,
        motion_score: float = 0.0,
        description: str = "",
    ) -> None:
        """Fuegt ein einzelnes Clip-Embedding hinzu."""
        if isinstance(embedding, list):
            embedding = np.array(embedding, dtype=np.float32)
        if len(embedding) != EMBEDDING_DIM:
            raise ValueError(
                f"Embedding muss {EMBEDDING_DIM} Dimensionen haben, "
                f"hat aber {len(embedding)}"
            )
        blob = embedding.astype(np.float32).tobytes()
        with self._write_lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO clip_embeddings "
                    "(id, video_path, scene_index, scene_start, scene_end, "
                    "motion_score, description, embedding) VALUES (?,?,?,?,?,?,?,?)",
                    (clip_id, video_path, scene_index, scene_start, scene_end,
                     motion_score, description, blob),
                )

    def add_embeddings_batch(self, entries: list[dict]) -> None:
        """Fuegt mehrere Embeddings auf einmal hinzu."""
        rows = []
        for entry in entries:
            emb = entry.get("embedding")
            if isinstance(emb, list):
                emb = np.array(emb, dtype=np.float32)
            if isinstance(emb, np.ndarray):
                if len(emb) != EMBEDDING_DIM:
                    raise ValueError(
                        f"Embedding-Dimension {len(emb)} != erwartet {EMBEDDING_DIM}."
                    )
                blob = emb.astype(np.float32).tobytes()
            else:
                continue
            rows.append((
                entry["id"], entry["video_path"], entry["scene_index"],
                entry["scene_start"], entry["scene_end"],
                entry.get("motion_score", 0.0), entry.get("description", ""),
                blob,
            ))
        if not rows:
            return
        with self._write_lock:
            with self._connect() as conn:
                conn.executemany(
                    "INSERT OR REPLACE INTO clip_embeddings "
                    "(id, video_path, scene_index, scene_start, scene_end, "
                    "motion_score, description, embedding) VALUES (?,?,?,?,?,?,?,?)",
                    rows,
                )
        logger.info("VectorDB: %d Embeddings gespeichert", len(rows))

    def search(
        self,
        query_embedding: list[float] | np.ndarray,
        top_k: int = 5,
        motion_filter: float | None = None,
    ) -> list[dict]:
        """Semantische Suche via Cosine-Similarity."""
        if isinstance(query_embedding, list):
            query_embedding = np.array(query_embedding, dtype=np.float32)
        query_norm = query_embedding / (np.linalg.norm(query_embedding) + 1e-8)

        sql = "SELECT id, video_path, scene_index, scene_start, scene_end, motion_score, description, embedding FROM clip_embeddings"
        params: list = []
        if motion_filter is not None:
            sql += " WHERE motion_score > ?"
            params.append(float(motion_filter))

        with self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        if not rows:
            return []

        results = []
        for row in rows:
            emb = np.frombuffer(row[7], dtype=np.float32)
            emb_norm = emb / (np.linalg.norm(emb) + 1e-8)
            similarity = float(np.dot(query_norm, emb_norm))
            distance = 1.0 - similarity
            results.append({
                "id": row[0],
                "video_path": row[1],
                "scene_index": row[2],
                "scene_start": row[3],
                "scene_end": row[4],
                "motion_score": row[5],
                "description": row[6],
                "_distance": distance,
            })

        results.sort(key=lambda x: x["_distance"])
        return results[:top_k]

    def search_by_text(
        self,
        text_embedding: list[float] | np.ndarray,
        top_k: int = 5,
    ) -> list[dict]:
        """Suche mit Text-Embedding."""
        return self.search(text_embedding, top_k=top_k)

    def count(self) -> int:
        """Gibt die Anzahl der Eintraege zurueck."""
        try:
            with self._connect() as conn:
                return conn.execute("SELECT COUNT(*) FROM clip_embeddings").fetchone()[0]
        except Exception:
            return 0

    def delete_by_video(self, video_path: str) -> None:
        """Loescht alle Embeddings fuer ein Video."""
        with self._write_lock:
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM clip_embeddings WHERE video_path = ?",
                    (video_path,),
                )

    def close(self) -> None:
        """Nichts zu tun — Connections werden per Context-Manager verwaltet."""
        pass
