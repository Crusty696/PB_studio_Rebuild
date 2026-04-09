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

# F-030: Singleton — verhindert desynchronisierte Write-Locks bei mehreren Instanzen
_instance: "VectorDBService | None" = None
_instance_lock = threading.Lock()


class VectorDBService:
    """Verwaltet Embeddings in SQLite fuer semantische Video-Clip-Suche.

    Ersetzt LanceDB komplett. Cosine-Similarity via numpy.
    Thread-safe via Write-Lock. Singleton — nur eine Instanz pro Prozess.
    """

    def __new__(cls, db_path: str | Path | None = None):
        global _instance
        if _instance is None:
            with _instance_lock:
                if _instance is None:
                    obj = super().__new__(cls)
                    obj._initialized = False
                    _instance = obj
        return _instance

    def __init__(self, db_path: str | Path | None = None):
        if getattr(self, "_initialized", False):
            return
        self.db_path = Path(db_path) if db_path else DB_FILE
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._write_lock = threading.Lock()
        
        # F-005 Fix: In-Memory Cache
        self._cache_matrix: np.ndarray | None = None
        self._cache_metadata: list[dict] | None = None
        self._cache_lock = threading.Lock()
        
        self._init_db()
        self._initialized = True

    def _invalidate_cache(self):
        """Invalidiert den In-Memory Cache nach Schreiboperationen."""
        with self._cache_lock:
            self._cache_matrix = None
            self._cache_metadata = None

    def _init_db(self):
        with sqlite3.connect(str(self.db_path)) as conn:
            # F-042 Fix: WAL Modus für parallele Zugriffe
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(_CREATE_SQL)
            conn.execute(_INDEX_SQL)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=DB_SQLITE_CONNECT_TIMEOUT_SEC)
        # F-042 Fix: WAL Modus auch für neue Connections sicherstellen
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

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
        """Fuegt ein einzelnes Clip-Embedding hinzu (F-007/F-043 Fix)."""
        if isinstance(embedding, list):
            embedding = np.array(embedding, dtype=np.float32)
        if len(embedding) != EMBEDDING_DIM:
            raise ValueError(
                f"Embedding muss {EMBEDDING_DIM} Dimensionen haben, "
                f"hat aber {len(embedding)}"
            )
        
        # F-043 Fix: ID-Berechnung zentralisiert
        composite_id = clip_id * 1_000_000 + scene_index
        blob = embedding.astype(np.float32).tobytes()
        
        with self._write_lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO clip_embeddings "
                    "(id, video_path, scene_index, scene_start, scene_end, "
                    "motion_score, description, embedding) VALUES (?,?,?,?,?,?,?,?)",
                    (composite_id, video_path, scene_index, scene_start, scene_end,
                     motion_score, description, blob),
                )
        self._invalidate_cache()

    def add_embeddings_batch(self, clip_id: int, entries: list[dict]) -> None:
        """Fuegt mehrere Embeddings auf einmal hinzu (Fix F-043: clip_id als Basis)."""
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
            
            # F-043 Fix: ID hier berechnen statt vom Caller zu erwarten
            idx = entry["scene_index"]
            composite_id = clip_id * 1_000_000 + idx
            
            rows.append((
                composite_id, entry["video_path"], idx,
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
        logger.info("VectorDB: %d Embeddings gespeichert fuer Clip %d", len(rows), clip_id)
        self._invalidate_cache()

    def search(
        self,
        query_embedding: list[float] | np.ndarray,
        top_k: int = 5,
        motion_filter: float | None = None,
    ) -> list[dict]:
        """Semantische Suche via Cosine-Similarity (F-005 Fix: Nutzt Cache)."""
        if isinstance(query_embedding, list):
            query_embedding = np.array(query_embedding, dtype=np.float32)
        
        # Query normalisieren
        query_norm = query_embedding / (np.linalg.norm(query_embedding) + 1e-8)

        # Cache prüfen oder laden
        with self._cache_lock:
            if self._cache_matrix is None:
                self._cache_matrix, self._cache_metadata = self._load_full_data()
            
            embeddings = self._cache_matrix
            metadata = self._cache_metadata

        if embeddings.size == 0:
            return []

        # Motion-Filter auf Metadaten anwenden (falls gesetzt)
        valid_indices = np.arange(len(metadata))
        if motion_filter is not None:
            valid_indices = [i for i, m in enumerate(metadata) if m["motion_score"] > motion_filter]
            if not valid_indices:
                return []
            embeddings = embeddings[valid_indices]

        # Vectorized similarity
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-8
        similarities = (embeddings / norms) @ query_norm
        
        # Top-K Indices
        k = min(top_k, len(similarities))
        top_sub_indices = np.argpartition(-similarities, k - 1)[:k]
        top_sub_indices = top_sub_indices[np.argsort(-similarities[top_sub_indices])]

        results = []
        for idx in top_sub_indices:
            orig_idx = valid_indices[idx]
            m = metadata[orig_idx]
            results.append({
                **m,
                "_distance": 1.0 - float(similarities[idx]),
            })
        return results

    def _load_full_data(self) -> tuple[np.ndarray, list[dict]]:
        """Lädt alle Daten aus der DB (interner Helper für Cache)."""
        sql = ("SELECT id, video_path, scene_index, scene_start, scene_end, "
               "motion_score, description, embedding FROM clip_embeddings")
        with self._connect() as conn:
            rows = conn.execute(sql).fetchall()

        if not rows:
            return np.empty((0, EMBEDDING_DIM), dtype=np.float32), []

        embeddings = np.vstack([np.frombuffer(row[7], dtype=np.float32) for row in rows])
        metadata = [
            {
                "id": row[0], "video_path": row[1], "scene_index": row[2],
                "scene_start": row[3], "scene_end": row[4],
                "motion_score": row[5], "description": row[6]
            }
            for row in rows
        ]
        return embeddings, metadata

    def search_by_text(
        self,
        text_embedding: list[float] | np.ndarray,
        top_k: int = 5,
    ) -> list[dict]:
        """Suche mit Text-Embedding."""
        return self.search(text_embedding, top_k=top_k)

    def get_all_embeddings(self) -> tuple[np.ndarray, list[dict]]:
        """Gibt ALLE Embeddings als Matrix + Metadaten zurueck.

        Returns:
            (embeddings_matrix[N, 1152], metadata_list[N])
            Jedes Metadaten-Dict hat: video_path, scene_index, scene_start,
            scene_end, motion_score, id
        """
        sql = ("SELECT id, video_path, scene_index, scene_start, scene_end, "
               "motion_score, embedding FROM clip_embeddings")
        with self._connect() as conn:
            rows = conn.execute(sql).fetchall()

        if not rows:
            return np.empty((0, EMBEDDING_DIM), dtype=np.float32), []

        embeddings = np.vstack(
            [np.frombuffer(row[6], dtype=np.float32) for row in rows]
        )
        metadata = [
            {
                "id": row[0],
                "video_path": row[1],
                "scene_index": row[2],
                "scene_start": row[3],
                "scene_end": row[4],
                "motion_score": row[5],
            }
            for row in rows
        ]
        return embeddings, metadata

    def count(self) -> int:
        """Gibt die Anzahl der Eintraege zurueck."""
        try:
            with self._connect() as conn:
                return conn.execute("SELECT COUNT(*) FROM clip_embeddings").fetchone()[0]
        except (OSError, RuntimeError, ValueError) as e:
            logger.warning("Counting embeddings in VectorDB: %s", e)
            return 0

    def delete_by_video(self, video_path: str) -> None:
        """Loescht alle Embeddings fuer ein Video."""
        with self._write_lock:
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM clip_embeddings WHERE video_path = ?",
                    (video_path,),
                )

    def delete_by_clip_ids(self, clip_ids: list[int]) -> None:
        """Loescht alle Embeddings deren clip_id (id // 1_000_000) in clip_ids liegt."""
        if not clip_ids:
            return
        with self._write_lock:
            with self._connect() as conn:
                placeholders = ",".join("?" for _ in clip_ids)
                conn.execute(
                    f"DELETE FROM clip_embeddings WHERE CAST(id / 1000000 AS INTEGER) IN ({placeholders})",
                    clip_ids,
                )
        logger.info("VectorDB: Embeddings fuer %d Clip-IDs geloescht", len(clip_ids))

    def delete_all(self) -> None:
        """Loescht alle Embeddings aus der Datenbank."""
        with self._write_lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM clip_embeddings")
        logger.info("VectorDB: Alle Embeddings geloescht")

    def close(self) -> None:
        """Nichts zu tun — Connections werden per Context-Manager verwaltet."""
        pass
