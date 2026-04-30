"""Studio Brain v2 persistence helpers.

This layer is app-internal product memory. It must not read Brain-Bug or any
external Obsidian vault.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import text

logger = logging.getLogger(__name__)


_SCHEMA_SQL: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS brain_entity (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_type TEXT NOT NULL,
        source_table TEXT NOT NULL,
        source_id INTEGER NOT NULL,
        title TEXT NOT NULL,
        summary TEXT,
        metadata_json TEXT,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        UNIQUE(entity_type, source_table, source_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_brain_entity_type ON brain_entity(entity_type)",
    """
    CREATE TABLE IF NOT EXISTS brain_fact (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entity_id INTEGER NOT NULL,
        fact_type TEXT NOT NULL,
        key TEXT NOT NULL,
        value_json TEXT NOT NULL,
        confidence REAL NOT NULL DEFAULT 1.0,
        source TEXT NOT NULL,
        created_at DATETIME NOT NULL,
        FOREIGN KEY(entity_id) REFERENCES brain_entity(id) ON DELETE CASCADE
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_brain_fact_entity ON brain_fact(entity_id)",
    "CREATE INDEX IF NOT EXISTS idx_brain_fact_key ON brain_fact(key)",
    """
    CREATE TABLE IF NOT EXISTS brain_decision (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER,
        decision_id INTEGER,
        audio_entity_id INTEGER,
        clip_entity_id INTEGER,
        why_json TEXT NOT NULL,
        why_text TEXT NOT NULL,
        created_at DATETIME NOT NULL,
        UNIQUE(decision_id),
        FOREIGN KEY(audio_entity_id) REFERENCES brain_entity(id) ON DELETE SET NULL,
        FOREIGN KEY(clip_entity_id) REFERENCES brain_entity(id) ON DELETE SET NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_brain_decision_run ON brain_decision(run_id)",
    """
    CREATE TABLE IF NOT EXISTS brain_memory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        memory_type TEXT NOT NULL,
        scope TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        confidence REAL NOT NULL DEFAULT 0.0,
        positive_count INTEGER NOT NULL DEFAULT 0,
        negative_count INTEGER NOT NULL DEFAULT 0,
        updated_at DATETIME NOT NULL,
        UNIQUE(memory_type, scope)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_brain_memory_scope ON brain_memory(scope)",
    """
    CREATE TABLE IF NOT EXISTS brain_note (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        body_md TEXT NOT NULL,
        source TEXT NOT NULL,
        linked_entity_id INTEGER,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL,
        UNIQUE(title, source),
        FOREIGN KEY(linked_entity_id) REFERENCES brain_entity(id) ON DELETE SET NULL
    )
    """,
)


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _json(value: Any) -> str:
    return json.dumps(value if value is not None else {}, ensure_ascii=False, sort_keys=True)


def ensure_brain_v2_schema(engine_or_connection: Any) -> None:
    """Create Brain v2 tables idempotently for tests and local bootstrap."""
    if hasattr(engine_or_connection, "begin"):
        with engine_or_connection.begin() as conn:
            for stmt in _SCHEMA_SQL:
                conn.execute(text(stmt))
        return
    for stmt in _SCHEMA_SQL:
        engine_or_connection.execute(text(stmt))


@dataclass(frozen=True)
class KnowledgeImportReport:
    imported_count: int
    note_ids: tuple[int, ...]


class BrainStore:
    """Single write API for Studio Brain v2 tables."""

    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory

    def _open_session(self) -> tuple[Any, bool]:
        session = self._session_factory()
        ownership = False
        if hasattr(session, "__enter__") and not hasattr(session, "execute"):
            session = session.__enter__()
            ownership = True
        return session, ownership

    @staticmethod
    def _close_session(session: Any, ownership: bool) -> None:
        if ownership:
            session.__exit__(None, None, None)
            return
        close = getattr(session, "close", None)
        if callable(close):
            close()

    def upsert_entity(
        self,
        entity_type: str,
        source_table: str,
        source_id: int,
        title: str,
        summary: str,
        metadata: dict[str, Any] | None,
    ) -> int:
        now = _now()
        payload = {
            "entity_type": str(entity_type),
            "source_table": str(source_table),
            "source_id": int(source_id),
            "title": str(title),
            "summary": str(summary or ""),
            "metadata_json": _json(metadata or {}),
            "now": now,
        }
        session, ownership = self._open_session()
        try:
            row = session.execute(
                text(
                    """
                    SELECT id FROM brain_entity
                    WHERE entity_type = :entity_type
                      AND source_table = :source_table
                      AND source_id = :source_id
                    """
                ),
                payload,
            ).fetchone()
            if row is None:
                result = session.execute(
                    text(
                        """
                        INSERT INTO brain_entity
                        (entity_type, source_table, source_id, title, summary,
                         metadata_json, created_at, updated_at)
                        VALUES
                        (:entity_type, :source_table, :source_id, :title, :summary,
                         :metadata_json, :now, :now)
                        RETURNING id
                        """
                    ),
                    payload,
                )
                entity_id = int(result.fetchone()[0])
            else:
                entity_id = int(row[0])
                session.execute(
                    text(
                        """
                        UPDATE brain_entity
                        SET title = :title,
                            summary = :summary,
                            metadata_json = :metadata_json,
                            updated_at = :now
                        WHERE id = :id
                        """
                    ),
                    {**payload, "id": entity_id},
                )
            session.commit()
            return entity_id
        finally:
            self._close_session(session, ownership)

    def add_fact(
        self,
        entity_id: int,
        fact_type: str,
        key: str,
        value: Any,
        confidence: float,
        source: str,
    ) -> int:
        session, ownership = self._open_session()
        try:
            result = session.execute(
                text(
                    """
                    INSERT INTO brain_fact
                    (entity_id, fact_type, key, value_json, confidence, source, created_at)
                    VALUES
                    (:entity_id, :fact_type, :key, :value_json, :confidence, :source, :now)
                    RETURNING id
                    """
                ),
                {
                    "entity_id": int(entity_id),
                    "fact_type": str(fact_type),
                    "key": str(key),
                    "value_json": _json(value),
                    "confidence": float(max(0.0, min(1.0, confidence))),
                    "source": str(source),
                    "now": _now(),
                },
            )
            fact_id = int(result.fetchone()[0])
            session.commit()
            return fact_id
        finally:
            self._close_session(session, ownership)

    def record_decision(
        self,
        run_id: int | None,
        decision_id: int | None,
        audio_entity_id: int | None,
        clip_entity_id: int | None,
        why_json: dict[str, Any],
        why_text: str,
    ) -> int:
        session, ownership = self._open_session()
        try:
            existing_id: int | None = None
            if decision_id is not None:
                row = session.execute(
                    text("SELECT id FROM brain_decision WHERE decision_id = :decision_id"),
                    {"decision_id": int(decision_id)},
                ).fetchone()
                existing_id = int(row[0]) if row else None
            payload = {
                "run_id": run_id,
                "decision_id": decision_id,
                "audio_entity_id": audio_entity_id,
                "clip_entity_id": clip_entity_id,
                "why_json": _json(why_json),
                "why_text": str(why_text or ""),
                "now": _now(),
            }
            if existing_id is None:
                result = session.execute(
                    text(
                        """
                        INSERT INTO brain_decision
                        (run_id, decision_id, audio_entity_id, clip_entity_id,
                         why_json, why_text, created_at)
                        VALUES
                        (:run_id, :decision_id, :audio_entity_id, :clip_entity_id,
                         :why_json, :why_text, :now)
                        RETURNING id
                        """
                    ),
                    payload,
                )
                brain_decision_id = int(result.fetchone()[0])
            else:
                session.execute(
                    text(
                        """
                        UPDATE brain_decision
                        SET run_id = :run_id,
                            audio_entity_id = :audio_entity_id,
                            clip_entity_id = :clip_entity_id,
                            why_json = :why_json,
                            why_text = :why_text
                        WHERE id = :id
                        """
                    ),
                    {**payload, "id": existing_id},
                )
                brain_decision_id = existing_id
            session.commit()
            return brain_decision_id
        finally:
            self._close_session(session, ownership)

    def import_knowledge_notes(self, knowledge_dir: str | Path) -> KnowledgeImportReport:
        root = Path(knowledge_dir)
        if not root.exists():
            return KnowledgeImportReport(imported_count=0, note_ids=())
        note_ids: list[int] = []
        session, ownership = self._open_session()
        try:
            for md_path in sorted(root.glob("*.md")):
                title = md_path.stem
                body = md_path.read_text(encoding="utf-8")
                now = _now()
                row = session.execute(
                    text("SELECT id FROM brain_note WHERE title = :title AND source = 'app_knowledge'"),
                    {"title": title},
                ).fetchone()
                if row is None:
                    result = session.execute(
                        text(
                            """
                            INSERT INTO brain_note
                            (title, body_md, source, linked_entity_id, created_at, updated_at)
                            VALUES (:title, :body_md, 'app_knowledge', NULL, :now, :now)
                            RETURNING id
                            """
                        ),
                        {"title": title, "body_md": body, "now": now},
                    )
                    note_ids.append(int(result.fetchone()[0]))
                else:
                    note_id = int(row[0])
                    session.execute(
                        text(
                            """
                            UPDATE brain_note
                            SET body_md = :body_md, updated_at = :now
                            WHERE id = :id
                            """
                        ),
                        {"id": note_id, "body_md": body, "now": now},
                    )
                    note_ids.append(note_id)
            session.commit()
        finally:
            self._close_session(session, ownership)
        return KnowledgeImportReport(imported_count=len(note_ids), note_ids=tuple(note_ids))

    def stats(self) -> dict[str, int]:
        session, ownership = self._open_session()
        try:
            out: dict[str, int] = {}
            for table in ("brain_entity", "brain_fact", "brain_decision", "brain_memory", "brain_note"):
                try:
                    out[table] = int(session.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar() or 0)
                except Exception:
                    out[table] = 0
            return out
        finally:
            self._close_session(session, ownership)
