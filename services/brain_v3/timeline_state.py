"""Brain V3 project state helpers.

Reads project-local ``brain_v3/state.db`` and resolves current timeline cuts
against the main PB Studio DB for UI feedback and learning previews.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, ContextManager

import database
import database.session as db_session_module
from services.brain_v3 import paths
from services.brain_v3.schemas.brain_v3_schemas import LearningSampleCut
from services.brain_v3.storage.migration_runner import migrate

logger = logging.getLogger(__name__)


SessionFactory = Callable[[], ContextManager[object]]


@dataclass(frozen=True)
class BrainV3TimelineCutMeta:
    cut_id: int
    clip_id: int
    start_time: float
    confidence: float | None


def default_project_root() -> Path:
    return Path(db_session_module.APP_ROOT)


def state_db_path(project_root: Path | None = None) -> Path:
    return paths.project_state_db_path(Path(project_root or default_project_root()))


def ensure_state_db(project_root: Path | None = None) -> Path:
    db_path = state_db_path(project_root)
    migrations_dir = Path(__file__).resolve().parent / "storage" / "sql_migrations" / "state"
    migrate(db_path, migrations_dir)
    return db_path


def load_current_timeline_metadata(
    project_root: Path | None = None,
) -> dict[tuple[int, int], BrainV3TimelineCutMeta]:
    """Return metadata keyed by ``(clip_id, rounded_start_ms)``."""
    db_path = ensure_state_db(project_root)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT c.id, c.clip_id, c.start_time, c.brain_v3_scores_json, c.metadata_json
            FROM timeline_cuts c
            JOIN timelines t ON t.id = c.timeline_id
            WHERE t.is_current = 1
            ORDER BY c.position_idx ASC, c.id ASC
            """
        ).fetchall()

    out: dict[tuple[int, int], BrainV3TimelineCutMeta] = {}
    for row in rows:
        try:
            clip_id = int(row[1])
        except (TypeError, ValueError):
            logger.debug("Brain V3 state: skip non-int clip_id=%r", row[1])
            continue
        start_time = float(row[2] or 0.0)
        out[(clip_id, _round_ms(start_time))] = BrainV3TimelineCutMeta(
            cut_id=int(row[0]),
            clip_id=clip_id,
            start_time=start_time,
            confidence=_extract_confidence(row[3], row[4]),
        )
    return out


def sync_current_timeline_from_entries(
    project_root: Path | None,
    entries: list[object],
) -> bool:
    """Create a Brain-V3 current timeline from main TimelineEntry rows if absent.

    Existing current Brain-V3 timelines are preserved. This avoids deleting
    feedback-linked state produced by the real pacing path.
    """
    db_path = ensure_state_db(project_root)
    entries = list(entries or [])
    audio_entries = [e for e in entries if getattr(e, "track", None) == "audio"]
    video_entries = [e for e in entries if getattr(e, "track", None) == "video"]
    if not audio_entries or not video_entries:
        return False

    with sqlite3.connect(db_path) as conn:
        existing = conn.execute(
            """
            SELECT COUNT(*)
            FROM timeline_cuts c
            JOIN timelines t ON t.id = c.timeline_id
            WHERE t.is_current = 1
            """
        ).fetchone()[0]
        if int(existing or 0) > 0:
            return False

        audio_clip_id = int(audio_entries[0].media_id)
        conn.execute("UPDATE timelines SET is_current = 0 WHERE is_current = 1")
        cur = conn.execute(
            "INSERT INTO timelines(name, audio_clip_id, created_at, config_json, is_current) "
            "VALUES (?, ?, ?, ?, 1)",
            (
                "main-timeline-sync",
                audio_clip_id,
                datetime.now(timezone.utc).isoformat(),
                '{"source": "main_timeline"}',
            ),
        )
        timeline_id = int(cur.lastrowid)
        for idx, entry in enumerate(sorted(video_entries, key=lambda e: float(e.start_time or 0.0))):
            start = float(getattr(entry, "start_time", 0.0) or 0.0)
            end_raw = getattr(entry, "end_time", None)
            end = float(end_raw) if end_raw is not None else start + 1.0
            clip_start = float(getattr(entry, "source_start", 0.0) or 0.0)
            conn.execute(
                """
                INSERT INTO timeline_cuts(
                    timeline_id, position_idx, clip_id, start_time, end_time,
                    clip_start, brain_v3_scores_json, metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timeline_id,
                    idx,
                    str(int(entry.media_id)),
                    start,
                    max(end, start),
                    clip_start,
                    '{"confidence": 0.5}',
                    '{"brain_v3_confidence": 0.5, "source": "main_timeline_sync"}',
                ),
            )
        conn.commit()
    return True


def load_learning_preview_samples(
    project_root: Path | None = None,
    session_factory: SessionFactory | None = None,
    n: int = 15,
) -> list[LearningSampleCut]:
    """Resolve current timeline cuts to real audio/video preview paths."""
    db_path = ensure_state_db(project_root)
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                c.id, c.clip_id, c.start_time, c.end_time, c.clip_start,
                c.brain_v3_scores_json, c.metadata_json, t.audio_clip_id
            FROM timeline_cuts c
            JOIN timelines t ON t.id = c.timeline_id
            WHERE t.is_current = 1
            ORDER BY c.position_idx ASC, c.id ASC
            LIMIT ?
            """,
            (max(0, int(n)),),
        ).fetchall()
    if not rows:
        return []

    sf = session_factory or database.nullpool_session
    audio_ids = sorted({int(r[7]) for r in rows if r[7] is not None})
    video_ids = []
    for r in rows:
        try:
            video_ids.append(int(r[1]))
        except (TypeError, ValueError):
            continue

    with sf() as session:
        audios = (
            {
                a.id: str(a.file_path) if a.file_path else None
                for a in session.query(database.AudioTrack).filter(
                    database.AudioTrack.id.in_(audio_ids),
                    database.AudioTrack.deleted_at.is_(None),
                ).all()
            }
            if audio_ids
            else {}
        )
        fallback_audio_path = _resolve_timeline_audio_path(
            session=session,
            project_root=project_root,
        )
        videos = (
            {
                v.id: _existing_media_path(v.proxy_path, v.file_path)
                for v in session.query(database.VideoClip).filter(
                    database.VideoClip.id.in_(video_ids),
                    database.VideoClip.deleted_at.is_(None),
                ).all()
            }
            if video_ids
            else {}
        )

    samples: list[LearningSampleCut] = []
    for r in rows:
        try:
            clip_id = int(r[1])
        except (TypeError, ValueError):
            continue
        audio = audios.get(int(r[7])) or fallback_audio_path
        video = videos.get(clip_id)
        if audio is None or video is None:
            continue
        audio_path = audio
        video_path = video
        confidence = _extract_confidence(r[5], r[6])
        duration = max(0.0, float(r[3] or 0.0) - float(r[2] or 0.0))
        samples.append(
            LearningSampleCut(
                cut_id=int(r[0]),
                audio_position_s=float(r[2] or 0.0),
                video_position_s=float(r[4] or 0.0),
                preview_duration_s=duration,
                clip_id=clip_id,
                audio_preview_path=audio_path,
                video_preview_path=video_path,
                has_preview=bool(audio_path or video_path),
                uncertainty=_confidence_to_uncertainty(confidence),
            )
        )
    return samples


def _resolve_timeline_audio_path(
    session: object,
    project_root: Path | None,
) -> str | None:
    query = (
        session.query(database.AudioTrack.file_path)
        .join(
            database.TimelineEntry,
            database.TimelineEntry.media_id == database.AudioTrack.id,
        )
        .join(
            database.Project,
            database.Project.id == database.TimelineEntry.project_id,
        )
        .filter(
            database.TimelineEntry.track == "audio",
            database.AudioTrack.deleted_at.is_(None),
        )
        .order_by(database.TimelineEntry.id.desc())
    )
    if project_root is not None:
        query = query.filter(database.Project.path == str(project_root))
    row = query.first()
    if row is None or not row[0]:
        return None
    return str(row[0])


def _existing_media_path(*candidates: object) -> str | None:
    fallback: str | None = None
    for raw in candidates:
        if not raw:
            continue
        value = str(raw)
        if fallback is None:
            fallback = value
        try:
            if Path(value).exists():
                return value
        except OSError:
            continue
    return fallback


def _extract_confidence(
    brain_v3_scores_json: str | None,
    metadata_json: str | None,
) -> float | None:
    for raw in (metadata_json, brain_v3_scores_json):
        data = _json_dict(raw)
        for key in ("brain_v3_confidence", "confidence"):
            if key in data:
                try:
                    return max(0.0, min(1.0, float(data[key])))
                except (TypeError, ValueError):
                    return None
    return None


def _confidence_to_uncertainty(confidence: float | None) -> float:
    if confidence is None:
        return 0.5
    return max(0.0, min(1.0, 1.0 - float(confidence)))


def _json_dict(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _round_ms(value: float) -> int:
    return int(round(float(value) * 1000.0))
