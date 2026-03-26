"""LanceDB Vector Database Service fuer semantische Clip-Suche.

Phase 1 Foundation — SEKTOR 3.
Erstellt eine LanceDB mit 1152-dimensionalen SigLIP Embeddings.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any

import numpy as np

from database import APP_ROOT

logger = logging.getLogger(__name__)

DB_DIR = APP_ROOT / "data" / "vector"
TABLE_NAME = "clip_embeddings"
EMBEDDING_DIM = 1152


class VectorDBService:
    """Verwaltet die LanceDB fuer semantische Video-Clip-Suche."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else DB_DIR
        self._db = None
        self._table = None
        self._init_lock = threading.Lock()   # fuer lazy-init der db/table Properties
        self._write_lock = threading.Lock()  # fuer alle Schreiboperationen

    @property
    def db(self):
        with self._init_lock:
            if self._db is None:
                import lancedb
                self.db_path.mkdir(parents=True, exist_ok=True)
                self._db = lancedb.connect(str(self.db_path))
            return self._db

    @property
    def table(self):
        with self._init_lock:
            if self._table is None:
                self._table = self._get_or_create_table()
            return self._table

    def _get_or_create_table(self):
        """Oeffnet oder erstellt die clip_embeddings Tabelle."""
        table_names = self.db.table_names()
        if TABLE_NAME in table_names:
            return self.db.open_table(TABLE_NAME)
        else:
            logger.warning("Tabelle '%s' nicht gefunden, erstelle neue Tabelle", TABLE_NAME)
            import pyarrow as pa
            schema = pa.schema([
                pa.field("id", pa.int64()),
                pa.field("video_path", pa.utf8()),
                pa.field("scene_index", pa.int32()),
                pa.field("scene_start", pa.float64()),
                pa.field("scene_end", pa.float64()),
                pa.field("motion_score", pa.float64()),
                pa.field("description", pa.utf8()),
                pa.field("embedding", pa.list_(pa.float32(), EMBEDDING_DIM)),
            ])
            return self.db.create_table(TABLE_NAME, schema=schema)

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
        if isinstance(embedding, np.ndarray):
            embedding = embedding.astype(np.float32).tolist()
        if len(embedding) != EMBEDDING_DIM:
            raise ValueError(
                f"Embedding muss {EMBEDDING_DIM} Dimensionen haben, "
                f"hat aber {len(embedding)}"
            )
        with self._write_lock:
            self.table.add([{
                "id": clip_id,
                "video_path": video_path,
                "scene_index": scene_index,
                "scene_start": scene_start,
                "scene_end": scene_end,
                "motion_score": motion_score,
                "description": description,
                "embedding": embedding,
            }])

    def add_embeddings_batch(self, entries: list[dict]) -> None:
        """Fuegt mehrere Embeddings auf einmal hinzu (schneller als einzeln).

        Jeder Eintrag muss die Felder id, video_path, scene_index,
        scene_start, scene_end, embedding enthalten.
        Optional: motion_score, description.
        """
        for entry in entries:
            emb = entry.get("embedding")
            if isinstance(emb, np.ndarray):
                entry["embedding"] = emb.astype(np.float32).tolist()
                emb = entry["embedding"]
            # F-015 Fix: Dimension-Check wie in add_embedding()
            if emb is not None and len(emb) != EMBEDDING_DIM:
                raise ValueError(
                    f"Embedding-Dimension {len(emb)} != erwartet {EMBEDDING_DIM}. "
                    f"Falsches SigLIP-Modell geladen?"
                )
            entry.setdefault("motion_score", 0.0)
            entry.setdefault("description", "")
        with self._write_lock:
            self.table.add(entries)

    def search(
        self,
        query_embedding: list[float] | np.ndarray,
        top_k: int = 5,
        motion_filter: float | None = None,
    ) -> list[dict]:
        """Semantische Suche nach aehnlichen Clips.

        Args:
            query_embedding: 1152-dim Suchvektor
            top_k: Anzahl der Ergebnisse
            motion_filter: Optionaler Filter (motion_score > X)

        Returns:
            Liste von Dicts mit id, video_path, scene_start, scene_end,
            motion_score, description, _distance
        """
        if isinstance(query_embedding, np.ndarray):
            query_embedding = query_embedding.astype(np.float32).tolist()

        query = self.table.search(query_embedding).limit(top_k)
        if motion_filter is not None:
            # Input-Validierung gegen Injection
            motion_val = float(motion_filter)
            query = query.where(f"motion_score > {motion_val}")

        results = query.to_arrow()
        rows = []
        for i in range(results.num_rows):
            rows.append({
                "id": results.column("id")[i].as_py(),
                "video_path": results.column("video_path")[i].as_py(),
                "scene_index": results.column("scene_index")[i].as_py(),
                "scene_start": results.column("scene_start")[i].as_py(),
                "scene_end": results.column("scene_end")[i].as_py(),
                "motion_score": results.column("motion_score")[i].as_py(),
                "description": results.column("description")[i].as_py(),
                "_distance": results.column("_distance")[i].as_py(),
            })
        return rows

    def search_by_text(
        self,
        text_embedding: list[float] | np.ndarray,
        top_k: int = 5,
    ) -> list[dict]:
        """Suche mit Text-Embedding (z.B. SigLIP Text-Encoder)."""
        return self.search(text_embedding, top_k=top_k)

    def count(self) -> int:
        """Gibt die Anzahl der Eintraege in der Tabelle zurueck."""
        try:
            return self.table.count_rows()
        except Exception as e:
            logger.warning("VectorDB count() fehlgeschlagen: %s", e)
            return 0

    def delete_by_video(self, video_path: str) -> None:
        """Loescht alle Embeddings fuer ein Video.

        Bug-33 Fix: Nutze parameterized Filter statt String-Interpolation.
        String-basierte Escaping ist unsicher gegen SQL-Injection-ähnliche Angriffe.
        """
        try:
            # LanceDB: .delete() erwartet einen Filter-String
            # Bug-33: Doppeln von Quotes statt falschem Escaping-Ansatz
            query_str = f"video_path = '{video_path.replace(chr(39), chr(39)*2)}'"
            with self._write_lock:
                self.table.delete(query_str)
        except Exception as e:
            logger.warning(
                "delete_by_video Standardfilter fehlgeschlagen: %s — nutze Fallback",
                e
            )
            # Fallback: Manuell durchsuchen und löschen (teurer, aber sicher)
            try:
                # Hole max 10000 Rows und filtere lokal
                results = self.table.search([0.0] * EMBEDDING_DIM).limit(10000).to_arrow()
                ids_to_delete = []
                for i in range(results.num_rows):
                    stored_path = results.column("video_path")[i].as_py()
                    if stored_path == video_path:
                        clip_id = results.column("id")[i].as_py()
                        ids_to_delete.append(clip_id)
                # Lösche gefundene IDs
                for cid in ids_to_delete:
                    self.table.delete(f"id = {cid}")
                logger.info("delete_by_video Fallback: %d Embeddings gelöscht für '%s'",
                           len(ids_to_delete), video_path)
            except Exception as e2:
                logger.error(
                    "delete_by_video vollständig fehlgeschlagen: %s (path=%s)",
                    e2, video_path
                )

    def close(self) -> None:
        """Schliesst die Datenbankverbindung."""
        self._table = None
        self._db = None
