"""SCHNITT workspace context aggregation.

Single small read-model for UI binders. It answers what SCHNITT can do right
now without forcing every subtab/controller to query DB state on its own.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models import (
    AudioTrack,
    Beatgrid,
    Project,
    Scene,
    TimelineEntry,
    VideoClip,
    WaveformData,
)


@dataclass(frozen=True, slots=True)
class SchnittDataContext:
    project_id: int | None
    project_path: str | None
    audio_id: int | None
    video_ids: tuple[int, ...]
    timeline_entry_count: int
    has_stems: bool
    has_waveform: bool
    has_beatgrid: bool
    has_video_analysis: bool
    missing_reasons: tuple[str, ...]

    @property
    def can_auto_edit(self) -> bool:
        return (
            self.project_id is not None
            and self.audio_id is not None
            and bool(self.video_ids)
            and self.has_beatgrid
        )

    @property
    def has_timeline(self) -> bool:
        return self.timeline_entry_count > 0


def build_schnitt_context(db_engine, project_id: int | None) -> SchnittDataContext:
    """Build a read-only SCHNITT context for one project.

    Args:
        db_engine: SQLAlchemy engine/proxy used by the active project.
        project_id: Active project id. ``None`` returns disabled context.
    """
    if project_id is None:
        return SchnittDataContext(
            project_id=None,
            project_path=None,
            audio_id=None,
            video_ids=(),
            timeline_entry_count=0,
            has_stems=False,
            has_waveform=False,
            has_beatgrid=False,
            has_video_analysis=False,
            missing_reasons=("Projekt fehlt",),
        )

    with Session(db_engine) as session:
        project_path = (
            session.query(Project.path)
            .filter(Project.id == project_id)
            .scalar()
        )

        audio = (
            session.query(
                AudioTrack.id,
                AudioTrack.stem_vocals_path,
                AudioTrack.stem_drums_path,
                AudioTrack.stem_bass_path,
                AudioTrack.stem_other_path,
            )
            .filter(
                AudioTrack.project_id == project_id,
                AudioTrack.deleted_at.is_(None),
            )
            .order_by(AudioTrack.id)
            .first()
        )
        audio_id = audio.id if audio is not None else None

        video_ids = tuple(
            row.id
            for row in session.query(VideoClip.id)
            .filter(
                VideoClip.project_id == project_id,
                VideoClip.deleted_at.is_(None),
            )
            .order_by(VideoClip.id)
            .all()
        )

        timeline_entry_count = (
            session.query(func.count(TimelineEntry.id))
            .filter(
                TimelineEntry.project_id == project_id,
                TimelineEntry.track == "video",
            )
            .scalar()
            or 0
        )

        has_stems = False
        has_waveform = False
        has_beatgrid = False
        if audio_id is not None:
            has_stems = any(
                bool(getattr(audio, attr, None))
                for attr in (
                    "stem_vocals_path",
                    "stem_drums_path",
                    "stem_bass_path",
                    "stem_other_path",
                )
            )
            has_waveform = (
                session.query(WaveformData.id)
                .filter(WaveformData.audio_track_id == audio_id)
                .first()
                is not None
            )
            has_beatgrid = (
                session.query(Beatgrid.id)
                .filter(Beatgrid.audio_track_id == audio_id)
                .first()
                is not None
            )

        has_video_analysis = False
        if video_ids:
            analyzed = (
                session.query(func.count(func.distinct(Scene.video_clip_id)))
                .filter(Scene.video_clip_id.in_(video_ids))
                .scalar()
                or 0
            )
            has_video_analysis = analyzed == len(video_ids)

    missing: list[str] = []
    if project_path is None:
        missing.append("Projekt fehlt")
    if audio_id is None:
        missing.append("Audio fehlt")
    if not video_ids:
        missing.append("Video fehlt")
    if audio_id is not None and not has_beatgrid:
        missing.append("Beatgrid fehlt")

    return SchnittDataContext(
        project_id=project_id,
        project_path=project_path,
        audio_id=audio_id,
        video_ids=video_ids,
        timeline_entry_count=timeline_entry_count,
        has_stems=has_stems,
        has_waveform=has_waveform,
        has_beatgrid=has_beatgrid,
        has_video_analysis=has_video_analysis,
        missing_reasons=tuple(missing),
    )
