from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from pathlib import Path
import zipfile

from sqlalchemy.orm import Session

from database.models import AnalysisArtifact, AnalysisJob, Project, ProjectSource
from services.storage_provenance.layout import StorageLayout


BUNDLE_VERSION = 1
MANIFEST_NAME = "manifest.json"


class ProjectBundleValidationError(ValueError):
    """Bundle manifest or payload failed validation."""


@dataclass(frozen=True)
class ProjectBundleExportResult:
    bundle_path: Path
    source_count: int
    job_count: int
    artifact_count: int
    file_count: int


@dataclass(frozen=True)
class ProjectBundleImportResult:
    project_id: int
    source_count: int
    job_count: int
    artifact_count: int
    file_count: int


class ProjectBundleService:
    """Export/import PB project provenance artifacts as ``.pbbundle`` zip."""

    def __init__(self, session: Session, *, storage_root: str | Path) -> None:
        self.session = session
        self.layout = StorageLayout(storage_root)

    def export_project(self, project_id: int, bundle_path: str | Path) -> ProjectBundleExportResult:
        project = self.session.get(Project, project_id)
        if project is None or project.deleted_at is not None:
            raise ValueError(f"Project not found: {project_id}")

        sources = (
            self.session.query(ProjectSource)
            .filter_by(project_id=project_id)
            .order_by(ProjectSource.source_sha256.asc())
            .all()
        )
        source_hashes = [source.source_sha256 for source in sources]
        jobs = (
            self.session.query(AnalysisJob)
            .filter(AnalysisJob.source_sha256.in_(source_hashes))
            .order_by(AnalysisJob.source_sha256.asc(), AnalysisJob.step_id.asc(), AnalysisJob.id.asc())
            .all()
            if source_hashes
            else []
        )
        artifacts = self._artifacts_for_jobs(jobs)
        storage_files = self._collect_storage_files(source_hashes)

        manifest = {
            "bundle_version": BUNDLE_VERSION,
            "created_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "project": {
                "name": project.name,
                "path": project.path,
                "resolution": project.resolution,
                "fps": project.fps,
            },
            "project_sources": [
                {
                    "source_sha256": source.source_sha256,
                    "current_source_path": source.current_source_path,
                    "last_seen_at": _dt_to_str(source.last_seen_at),
                }
                for source in sources
            ],
            "analysis_jobs": [_job_to_manifest(job) for job in jobs],
            "analysis_artifacts": [_artifact_to_manifest(artifact) for artifact in artifacts],
            "storage_files": [
                {
                    "path": zip_name,
                    "sha256": _file_sha256(file_path),
                    "bytes": file_path.stat().st_size,
                }
                for zip_name, file_path in storage_files
            ],
        }

        output = Path(bundle_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(MANIFEST_NAME, json.dumps(manifest, indent=2, sort_keys=True))
            for zip_name, file_path in storage_files:
                zf.write(file_path, zip_name)

        return ProjectBundleExportResult(
            bundle_path=output,
            source_count=len(sources),
            job_count=len(jobs),
            artifact_count=len(artifacts),
            file_count=len(storage_files),
        )

    def import_project(self, bundle_path: str | Path, *, project_path: str | Path) -> ProjectBundleImportResult:
        bundle = Path(bundle_path)
        with zipfile.ZipFile(bundle) as zf:
            manifest = self._load_manifest(zf)
            self._verify_storage_files(zf, manifest)
            project = self._create_project(manifest["project"], project_path)
            self.session.flush()
            source_count = self._import_project_sources(manifest, project.id)
            job_count, artifact_count = self._import_jobs_and_artifacts(manifest)
            file_count = self._extract_storage_files(zf, manifest)
            self.session.commit()

        return ProjectBundleImportResult(
            project_id=project.id,
            source_count=source_count,
            job_count=job_count,
            artifact_count=artifact_count,
            file_count=file_count,
        )

    def _load_manifest(self, zf: zipfile.ZipFile) -> dict:
        try:
            raw = zf.read(MANIFEST_NAME)
        except KeyError as exc:
            raise ProjectBundleValidationError("Bundle missing manifest.json") from exc
        try:
            manifest = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ProjectBundleValidationError("Bundle manifest is not valid JSON") from exc
        if manifest.get("bundle_version") != BUNDLE_VERSION:
            raise ProjectBundleValidationError(f"Unsupported bundle version: {manifest.get('bundle_version')!r}")
        for key in ("project", "project_sources", "analysis_jobs", "analysis_artifacts", "storage_files"):
            if key not in manifest:
                raise ProjectBundleValidationError(f"Bundle manifest missing key: {key}")
        return manifest

    def _verify_storage_files(self, zf: zipfile.ZipFile, manifest: dict) -> None:
        for entry in manifest["storage_files"]:
            zip_name = entry["path"]
            try:
                data = zf.read(zip_name)
            except KeyError as exc:
                raise ProjectBundleValidationError(f"Bundle missing storage file: {zip_name}") from exc
            digest = hashlib.sha256(data).hexdigest()
            if digest != entry["sha256"]:
                raise ProjectBundleValidationError(f"SHA mismatch for {zip_name}")

    def _create_project(self, data: dict, project_path: str | Path) -> Project:
        project = Project(
            name=str(data["name"]),
            path=str(project_path),
            resolution=str(data.get("resolution") or "1920x1080"),
            fps=float(data.get("fps") or 30.0),
        )
        self.session.add(project)
        return project

    def _import_project_sources(self, manifest: dict, project_id: int) -> int:
        count = 0
        for item in manifest["project_sources"]:
            row = ProjectSource(
                project_id=project_id,
                source_sha256=item["source_sha256"],
                current_source_path=item["current_source_path"],
                last_seen_at=_str_to_dt(item.get("last_seen_at")),
            )
            self.session.add(row)
            count += 1
        return count

    def _import_jobs_and_artifacts(self, manifest: dict) -> tuple[int, int]:
        job_key_to_id: dict[str, int] = {}
        imported_jobs = 0
        imported_artifacts = 0

        for item in manifest["analysis_jobs"]:
            existing = (
                self.session.query(AnalysisJob)
                .filter_by(
                    source_sha256=item["source_sha256"],
                    step_id=item["step_id"],
                    step_version=item["step_version"],
                    params_hash=item["params_hash"],
                )
                .one_or_none()
            )
            if existing is None:
                existing = AnalysisJob(
                    source_sha256=item["source_sha256"],
                    step_id=item["step_id"],
                    step_version=item["step_version"],
                    params_hash=item["params_hash"],
                    status=item["status"],
                    produced_by_model=item.get("produced_by_model"),
                    produced_by_model_version=item.get("produced_by_model_version"),
                    coverage_percent=item.get("coverage_percent"),
                    started_at=_str_to_dt(item.get("started_at")),
                    finished_at=_str_to_dt(item.get("finished_at")),
                    duration_seconds=item.get("duration_seconds"),
                    error=item.get("error"),
                )
                self.session.add(existing)
                self.session.flush()
                imported_jobs += 1
            job_key_to_id[item["bundle_job_key"]] = existing.id

        for item in manifest["analysis_artifacts"]:
            job_id = job_key_to_id[item["bundle_job_key"]]
            existing_artifact = (
                self.session.query(AnalysisArtifact)
                .filter_by(job_id=job_id, artifact_role=item["artifact_role"], path=item["path"])
                .one_or_none()
            )
            if existing_artifact is None:
                self.session.add(
                    AnalysisArtifact(
                        job_id=job_id,
                        artifact_type=item["artifact_type"],
                        artifact_role=item["artifact_role"],
                        path=item["path"],
                        bytes=item.get("bytes"),
                        sha256=item.get("sha256"),
                    )
                )
                imported_artifacts += 1
        return imported_jobs, imported_artifacts

    def _extract_storage_files(self, zf: zipfile.ZipFile, manifest: dict) -> int:
        storage_root = self.layout.storage_root.absolute()
        copied = 0
        for entry in manifest["storage_files"]:
            zip_name = entry["path"]
            relative = Path(zip_name).relative_to("storage")
            target = (storage_root / relative).absolute()
            try:
                target.relative_to(storage_root)
            except ValueError as exc:
                raise ProjectBundleValidationError(f"Storage path escapes root: {zip_name}") from exc
            if target.exists():
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(zip_name))
            copied += 1
        return copied

    def _artifacts_for_jobs(self, jobs: list[AnalysisJob]) -> list[AnalysisArtifact]:
        job_ids = [job.id for job in jobs]
        if not job_ids:
            return []
        return (
            self.session.query(AnalysisArtifact)
            .filter(AnalysisArtifact.job_id.in_(job_ids))
            .order_by(AnalysisArtifact.job_id.asc(), AnalysisArtifact.path.asc())
            .all()
        )

    def _collect_storage_files(self, source_hashes: list[str]) -> list[tuple[str, Path]]:
        files: list[tuple[str, Path]] = []
        for source_sha in source_hashes:
            root = self.layout.source_root(source_sha)
            if not root.exists():
                continue
            for file_path in sorted(path for path in root.rglob("*") if path.is_file()):
                relative = file_path.relative_to(self.layout.storage_root)
                files.append((f"storage/{relative.as_posix()}", file_path))
        return files


def _job_to_manifest(job: AnalysisJob) -> dict:
    return {
        "bundle_job_key": _job_key(job),
        "source_sha256": job.source_sha256,
        "step_id": job.step_id,
        "step_version": job.step_version,
        "params_hash": job.params_hash,
        "status": job.status,
        "produced_by_model": job.produced_by_model,
        "produced_by_model_version": job.produced_by_model_version,
        "coverage_percent": job.coverage_percent,
        "started_at": _dt_to_str(job.started_at),
        "finished_at": _dt_to_str(job.finished_at),
        "duration_seconds": job.duration_seconds,
        "error": job.error,
    }


def _artifact_to_manifest(artifact: AnalysisArtifact) -> dict:
    return {
        "bundle_job_key": _job_key(artifact.job),
        "artifact_type": artifact.artifact_type,
        "artifact_role": artifact.artifact_role,
        "path": artifact.path,
        "bytes": artifact.bytes,
        "sha256": artifact.sha256,
    }


def _job_key(job: AnalysisJob) -> str:
    return "|".join([job.source_sha256, job.step_id, job.step_version, job.params_hash])


def _dt_to_str(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _str_to_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value[:-1] if value.endswith("Z") else value
    return datetime.fromisoformat(normalized)


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
