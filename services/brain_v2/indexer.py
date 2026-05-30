"""Brain v2 project indexer."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy import text

from services.brain_v2.store import BrainStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BrainIndexReport:
    entities_upserted: int = 0
    facts_added: int = 0
    notes_imported: int = 0
    errors: list[str] = field(default_factory=list)


class BrainIndexer:
    def __init__(self, session_factory: Callable[[], Any]) -> None:
        self._session_factory = session_factory
        self._store = BrainStore(session_factory)

    def index_project(self) -> BrainIndexReport:
        entities = 0
        facts = 0
        errors: list[str] = []
        session = self._session_factory()
        close = getattr(session, "close", None)
        try:
            present = self._table_names(session)
            if "audio_tracks" in present:
                e, f = self._index_audio_tracks(session)
                entities += e
                facts += f
            if "structure_segments" in present:
                e, f = self._index_structure_segments(session)
                entities += e
                facts += f
            if "video_clips" in present:
                e, f = self._index_video_clips(session)
                entities += e
                facts += f
            if "scenes" in present:
                e, f = self._index_scenes(session, present)
                entities += e
                facts += f
        except Exception as exc:
            errors.append(str(exc))
            logger.warning("BrainV2 index_project failed: %s", exc)
        finally:
            if callable(close):
                close()
        return BrainIndexReport(entities_upserted=entities, facts_added=facts, errors=errors)

    @staticmethod
    def _table_names(session: Any) -> set[str]:
        rows = session.execute(text("SELECT name FROM sqlite_master WHERE type='table'")).fetchall()
        return {str(row[0]) for row in rows}

    def _index_audio_tracks(self, session: Any) -> tuple[int, int]:
        rows = session.execute(text("SELECT * FROM audio_tracks")).mappings().all()
        entities = facts = 0
        for r in rows:
            entity_id = self._store.upsert_entity(
                "track",
                "audio_tracks",
                int(r["id"]),
                r.get("title") or self._basename(r.get("file_path")) or f"Audio {r['id']}",
                f"BPM {r.get('bpm')}" if r.get("bpm") is not None else "",
                {
                    "file_path": r.get("file_path"),
                    "duration": r.get("duration"),
                    "bpm": r.get("bpm"),
                    "mood": r.get("mood"),
                    "genre": r.get("genre"),
                },
            )
            entities += 1
            for key in ("bpm", "mood", "genre", "duration"):
                if r.get(key) is not None:
                    self._store.add_fact(entity_id, "audio", key, r.get(key), 1.0, "brain_indexer")
                    facts += 1
        return entities, facts

    def _index_structure_segments(self, session: Any) -> tuple[int, int]:
        rows = session.execute(text("SELECT * FROM structure_segments")).mappings().all()
        entities = facts = 0
        for r in rows:
            label = r.get("label") or f"Section {r['id']}"
            entity_id = self._store.upsert_entity(
                "section",
                "structure_segments",
                int(r["id"]),
                str(label),
                f"{r.get('start_time', 0)}-{r.get('end_time', 0)} sec",
                dict(r),
            )
            entities += 1
            for key in ("label", "energy", "confidence", "audio_track_id"):
                if r.get(key) is not None:
                    self._store.add_fact(entity_id, "section", key, r.get(key), float(r.get("confidence") or 1.0), "brain_indexer")
                    facts += 1
        return entities, facts

    def _index_video_clips(self, session: Any) -> tuple[int, int]:
        rows = session.execute(text("SELECT * FROM video_clips")).mappings().all()
        entities = facts = 0
        for r in rows:
            entity_id = self._store.upsert_entity(
                "clip",
                "video_clips",
                int(r["id"]),
                self._basename(r.get("file_path")) or f"Clip {r['id']}",
                "",
                {"file_path": r.get("file_path"), "duration": r.get("duration")},
            )
            entities += 1
            if r.get("duration") is not None:
                self._store.add_fact(entity_id, "clip", "duration", r.get("duration"), 1.0, "brain_indexer")
                facts += 1
        return entities, facts

    def _index_scenes(self, session: Any, present: set[str]) -> tuple[int, int]:
        rows = session.execute(text("SELECT * FROM scenes")).mappings().all()
        tags_by_scene: dict[int, dict[str, Any]] = {}
        if "struct_clip_tags" in present:
            for tag in session.execute(text("SELECT * FROM struct_clip_tags")).mappings().all():
                tags_by_scene[int(tag["scene_id"])] = dict(tag)
        bucket_names: dict[int, str] = {}
        if "struct_style_bucket" in present:
            for bucket in session.execute(text("SELECT id, name FROM struct_style_bucket")).mappings().all():
                bucket_names[int(bucket["id"])] = str(bucket["name"])
        entities = facts = 0
        for r in rows:
            meta = dict(r)
            tag = tags_by_scene.get(int(r["id"]))
            if tag:
                meta.update({"tag": tag, "style_bucket_name": bucket_names.get(int(tag["style_bucket_id"]))})
            entity_id = self._store.upsert_entity(
                "scene",
                "scenes",
                int(r["id"]),
                r.get("label") or f"Scene {r['id']}",
                f"{r.get('start_time', 0)}-{r.get('end_time', 0)} sec",
                meta,
            )
            entities += 1
            if r.get("energy") is not None:
                self._store.add_fact(entity_id, "scene", "motion_score", r.get("energy"), 1.0, "brain_indexer")
                facts += 1
            if r.get("ai_mood") is not None:
                self._store.add_fact(entity_id, "scene", "ai_mood", r.get("ai_mood"), 1.0, "brain_indexer")
                facts += 1
            if tag:
                tag_facts = (
                    ("role", tag.get("role"), tag.get("role_confidence")),
                    ("mood", tag.get("mood_refined"), tag.get("mood_confidence")),
                    ("style_bucket", bucket_names.get(int(tag["style_bucket_id"]), tag.get("style_bucket_id")), 1.0),
                    ("style_distance", tag.get("style_distance"), 1.0),
                )
                for key, value, confidence in tag_facts:
                    if value is not None:
                        self._store.add_fact(entity_id, "clip_tag", key, value, float(confidence or 1.0), "brain_indexer")
                        facts += 1
        return entities, facts

    @staticmethod
    def _basename(path: Any) -> str:
        if not path:
            return ""
        return str(path).replace("\\", "/").rstrip("/").split("/")[-1]
