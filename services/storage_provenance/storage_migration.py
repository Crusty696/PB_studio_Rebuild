from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import logging
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from database.models import (
    AnalysisArtifact,
    AnalysisJob,
    AudioTrack,
    Project,
    ProjectSource,
    VideoClip,
)
from services.storage_provenance.layout import StorageLayout, create_directory_link
from services.storage_provenance.source_identity import compute_source_sha256
from services.storage_provenance.source_manifest import record_manifest_job

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, int, int], None]


@dataclass(frozen=True)
class StorageMigrationResult:
    audio_tracks: int = 0
    video_clips: int = 0
    skipped_missing_sources: int = 0


class StorageMigrationService:
    """Register existing project-local outputs in the global by_sha layout."""

    def __init__(
        self,
        session: Session,
        *,
        storage_root: str | Path,
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        self.session = session
        self.layout = StorageLayout(storage_root)
        self.storage_root = storage_root
        self.progress_callback = progress_callback

    def _record_manifest(
        self,
        project_id: int,
        source_sha: str,
        job: AnalysisJob,
        artifacts: dict[str, str | Path] | None = None,
    ) -> None:
        """B-539: mirror the provenance job into the global by_sha manifest so
        cross-project reuse works across per-project DBs. Best-effort.

        B-579: also persist the real artifact paths so reuse resolves the actual
        files instead of assuming the by_sha layout."""
        try:
            project = self.session.get(Project, project_id)
            record_manifest_job(
                self.storage_root,
                source_sha,
                project_id=project_id,
                project_name=project.name if project is not None else "unbekannt",
                project_path=project.path if project is not None else str(project_id),
                step_id=job.step_id,
                model=job.produced_by_model,
                model_version=job.produced_by_model_version,
                finished_at=job.finished_at,
                artifacts=artifacts,
            )
        except Exception as e:  # never break migration on manifest write
            logger.warning("B-545: provenance manifest write failed (project=%s): %s", project_id, e)

    def migrate_existing_outputs(self) -> StorageMigrationResult:
        # B-623: nur die von den Migrations-Helfern gelesenen Skalar-Spalten laden
        # statt voller ORM-Rows. session.query(...).all() lud sonst via
        # lazy='joined' die grossen JSON-Blob-Relationships mit
        # (AudioTrack.beatgrid/waveform_data, VideoClip.scenes) und fror den Thread ein.
        audio_tracks = self.session.execute(
            select(
                AudioTrack.file_path,
                AudioTrack.stem_vocals_path,
                AudioTrack.stem_drums_path,
                AudioTrack.stem_bass_path,
                AudioTrack.stem_other_path,
                AudioTrack.project_id,
            )
        ).all()
        video_clips = self.session.execute(
            select(
                VideoClip.file_path,
                VideoClip.proxy_path,
                VideoClip.embeddings_path,
                VideoClip.motion_path,
                VideoClip.project_id,
            )
        ).all()

        audio_count = 0
        video_count = 0
        skipped = 0

        for index, track in enumerate(audio_tracks, start=1):
            self._progress("audio", index, len(audio_tracks))
            migrated = self._migrate_audio_track(track)
            if migrated is None:
                skipped += 1
            elif migrated:
                audio_count += 1

        for index, clip in enumerate(video_clips, start=1):
            self._progress("video", index, len(video_clips))
            migrated = self._migrate_video_clip(clip)
            if migrated is None:
                skipped += 1
            elif migrated:
                video_count += 1

        self.session.commit()
        return StorageMigrationResult(
            audio_tracks=audio_count,
            video_clips=video_count,
            skipped_missing_sources=skipped,
        )

    def _migrate_audio_track(self, track: AudioTrack) -> bool | None:
        source = Path(track.file_path)
        if not source.is_file():
            return None

        stem_paths = {
            "vocals_stem": track.stem_vocals_path,
            "drums_stem": track.stem_drums_path,
            "bass_stem": track.stem_bass_path,
            "other_stem": track.stem_other_path,
        }
        existing_stems = {
            role: Path(path)
            for role, path in stem_paths.items()
            if path and Path(path).is_file()
        }
        if not existing_stems:
            return False

        source_sha = compute_source_sha256(source, media_type="audio", mode="strict")
        source_root = self.layout.ensure_source_root(source_sha)
        first_stem_dir = next(iter(existing_stems.values())).parent
        create_directory_link(source_root / "audio" / "stems", first_stem_dir)
        self._upsert_project_source(track.project_id, source_sha, source)
        job = self._upsert_job(source_sha, "audio.v2.stems", "1", "legacy-v2-stems", "done")
        # B-579: record the real stem paths (stripped of the "_stem" role suffix so
        # reuse keys match vocals/drums/bass/other) for cross-project reuse.
        self._record_manifest(
            track.project_id,
            source_sha,
            job,
            {role.replace("_stem", ""): str(path) for role, path in existing_stems.items()},
        )

        for role, stem_path in existing_stems.items():
            linked_path = source_root / "audio" / "stems" / stem_path.name
            self._upsert_artifact(
                job,
                artifact_type="stem",
                artifact_role=role,
                rel_path=self.layout.relative_artifact_path(source_sha, linked_path),
                file_path=stem_path,
            )
        return True

    def _migrate_video_clip(self, clip: VideoClip) -> bool | None:
        source = Path(clip.file_path)
        if not source.is_file():
            return None

        outputs = {
            "proxy": clip.proxy_path,
            "embeddings": clip.embeddings_path,
            "motion": clip.motion_path,
        }
        existing_outputs = {
            role: Path(path)
            for role, path in outputs.items()
            if path and Path(path).is_file()
        }
        if not existing_outputs:
            return False

        source_sha = compute_source_sha256(source, media_type="video", mode="strict")
        self.layout.ensure_source_root(source_sha)
        self._upsert_project_source(clip.project_id, source_sha, source)
        job = self._upsert_job(source_sha, "video.plan_a.outputs", "1", "legacy-plan-a", "done")
        # B-579: record the real proxy/embeddings/motion paths for cross-project reuse.
        self._record_manifest(
            clip.project_id,
            source_sha,
            job,
            {role: str(path) for role, path in existing_outputs.items()},
        )

        rel_names = {
            "proxy": "video/proxy.mp4",
            "embeddings": "video/embeddings.npy",
            "motion": "video/motion.json",
        }
        type_names = {
            "proxy": "video",
            "embeddings": "npy",
            "motion": "json",
        }
        for role, output_path in existing_outputs.items():
            self._upsert_artifact(
                job,
                artifact_type=type_names[role],
                artifact_role=role,
                rel_path=rel_names[role],
                file_path=output_path,
            )
        return True

    def _upsert_project_source(self, project_id: int, source_sha: str, source_path: Path) -> ProjectSource:
        row = (
            self.session.query(ProjectSource)
            .filter_by(project_id=project_id, source_sha256=source_sha)
            .one_or_none()
        )
        if row is None:
            row = ProjectSource(
                project_id=project_id,
                source_sha256=source_sha,
                current_source_path=str(source_path),
                last_seen_at=datetime.utcnow(),
            )
            self.session.add(row)
        else:
            row.current_source_path = str(source_path)
            row.last_seen_at = datetime.utcnow()
        return row

    def _upsert_job(
        self,
        source_sha: str,
        step_id: str,
        step_version: str,
        params_hash: str,
        status: str,
    ) -> AnalysisJob:
        row = (
            self.session.query(AnalysisJob)
            .filter_by(
                source_sha256=source_sha,
                step_id=step_id,
                step_version=step_version,
                params_hash=params_hash,
            )
            .one_or_none()
        )
        if row is None:
            row = AnalysisJob(
                source_sha256=source_sha,
                step_id=step_id,
                step_version=step_version,
                params_hash=params_hash,
                status=status,
            )
            self.session.add(row)
            self.session.flush()
        else:
            row.status = status
        return row

    def _upsert_artifact(
        self,
        job: AnalysisJob,
        *,
        artifact_type: str,
        artifact_role: str,
        rel_path: str,
        file_path: Path,
    ) -> AnalysisArtifact:
        row = (
            self.session.query(AnalysisArtifact)
            .filter_by(job_id=job.id, artifact_role=artifact_role, path=rel_path)
            .one_or_none()
        )
        if row is None:
            row = AnalysisArtifact(
                job_id=job.id,
                artifact_type=artifact_type,
                artifact_role=artifact_role,
                path=rel_path,
            )
            self.session.add(row)
        row.bytes = file_path.stat().st_size
        row.sha256 = _file_sha256(file_path)
        return row

    def _progress(self, phase: str, index: int, total: int) -> None:
        if self.progress_callback is not None:
            self.progress_callback(phase, index, total)


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
