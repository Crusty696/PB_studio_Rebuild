from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import logging
import os
import time
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

# B-814: Abstand zwischen Fortschrittsmeldungen. Gleicher Wert wie in B-810
# (services/storage_provenance/file_tracking.py) — beide Laeufe haengen am
# selben Projekt-Open und sollen sich im Log gleich verhalten.
_MIGRATION_LOG_INTERVAL_S = 5.0
# B-816: ab dieser Groesse wird VOR dem Pruefen gemeldet — eine einzelne
# grosse Datei kann laenger dauern als das Meldeintervall, dann greift die
# Zeitschwelle nie und der Lauf wirkt eingefroren.
_GROSSE_DATEI_MB = 150.0


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
        # B-814: (project_id, pfad) -> Liste bekannter (sha, bytes, mtime_ns).
        # Wird beim ersten Zugriff mit EINER Query gefuellt, siehe
        # ``_source_fingerprints``.
        self._source_fingerprints_cache: dict[
            tuple[int, str], list[tuple[str, int | None, int | None]]
        ] | None = None

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

        # B-814: dieser Lauf war komplett stumm.
        #
        # ``migrate_existing_outputs`` laeuft bei JEDEM ``open_project`` —
        # direkt vor der Quellen-Reparatur aus B-810, im selben try-Block
        # (services/project_manager.py:464). Pro Audiotrack/Videoclip mit
        # vorhandenen Outputs berechnet es ``compute_source_sha256(...,
        # mode="strict")``, also einen Hash ueber die KOMPLETTE Quelldatei.
        # An der realen Projekt-DB ``outputs/test-tabelle`` gemessen: 123
        # Clips mit existierender Quelle und existierenden Outputs,
        # zusammen 1,16 GB, die bei jedem Oeffnen vollstaendig gelesen und
        # gehasht werden.
        #
        # ``progress_callback`` bleibt dabei wirkungslos: KEIN Aufrufer im
        # Produktivpfad setzt ihn (``ensure_schnitt_audio_adapter`` uebergibt
        # keinen), und das Modul hatte ausser einem ``logger.warning`` keine
        # einzige Ausgabe. Historischer Beleg: in
        # ``logs/freeze_stacks_BEFORE_FIX.log`` steht der blockierte
        # Main-Thread 14-mal genau in dieser Funktion.
        #
        # NACHTRAG B-814 (Alembic ``a3b4c5d6e7f8``): der Aufwand ist jetzt
        # gesenkt. ``project_sources`` hat mit ``source_bytes`` /
        # ``source_mtime_ns`` den Stat-Fingerabdruck, der bei den Artefakten
        # ueber ``bytes`` laengst existiert (siehe ``_upsert_artifact``).
        # ``_source_sha`` kuerzt damit ab: Groesse UND mtime unveraendert =>
        # gespeicherten Hash wiederverwenden, Datei gar nicht erst oeffnen.
        total = len(audio_tracks) + len(video_clips)
        start = time.monotonic()
        letzte_meldung = start
        logger.info(
            "B-814: Storage-Migration beim Projekt-Open — pruefe %d Audiotrack(s) "
            "und %d Videoclip(s) ...",
            len(audio_tracks), len(video_clips),
        )

        def _melde(phase: str, index: int, pfad=None) -> None:
            """B-816: melden BEVOR die teure Arbeit beginnt, nicht nur danach.

            Live gemessen 2026-08-12 am echten Projekt: trotz 5-s-Intervall gab
            es beim ersten Open **17 Sekunden ohne jede Logzeile**. Grund: die
            Meldung lag ZWISCHEN den Clips. Dauert das Hashen einer einzelnen
            grossen Videodatei 17 s, schweigt es genau so lange — das
            Zeitintervall kann dort gar nicht greifen.

            Deshalb bei grossen Dateien immer vorher ansagen, was jetzt kommt.
            Damit weiss der Nutzer, dass gearbeitet wird und woran.
            """
            nonlocal letzte_meldung
            jetzt = time.monotonic()
            gross_mb = 0.0
            if pfad:
                try:
                    gross_mb = Path(pfad).stat().st_size / 1048576
                except OSError:
                    gross_mb = 0.0
            faellig = jetzt - letzte_meldung >= _MIGRATION_LOG_INTERVAL_S
            if faellig or gross_mb >= _GROSSE_DATEI_MB:
                if gross_mb >= _GROSSE_DATEI_MB:
                    logger.info(
                        "B-814: %s %d/%d — pruefe %.0f MB (%.0fs) ...",
                        phase, index, total, gross_mb, jetzt - start,
                    )
                else:
                    logger.info(
                        "B-814: %s %d/%d geprueft (%.0fs) — Migration laeuft ...",
                        phase, index, total, jetzt - start,
                    )
                letzte_meldung = jetzt

        for index, track in enumerate(audio_tracks, start=1):
            self._progress("audio", index, len(audio_tracks))
            _melde("Audio", index, getattr(track, "file_path", None))
            migrated = self._migrate_audio_track(track)
            if migrated is None:
                skipped += 1
            elif migrated:
                audio_count += 1

        for index, clip in enumerate(video_clips, start=1):
            self._progress("video", index, len(video_clips))
            _melde("Video", len(audio_tracks) + index,
                   getattr(clip, "file_path", None))
            migrated = self._migrate_video_clip(clip)
            if migrated is None:
                skipped += 1
            elif migrated:
                video_count += 1

        self.session.commit()
        logger.info(
            "B-814: Storage-Migration fertig — %d Audio, %d Video migriert, "
            "%d uebersprungen (Quelle fehlt), %.1fs.",
            audio_count, video_count, skipped, time.monotonic() - start,
        )
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

        source_sha = self._source_sha(track.project_id, source, "audio")
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

        source_sha = self._source_sha(clip.project_id, source, "video")
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

    # ------------------------------------------------------------------
    # B-814: Quell-Hash-Kurzschluss
    # ------------------------------------------------------------------

    def _source_fingerprints(
        self,
    ) -> dict[tuple[int, str], list[tuple[str, int | None, int | None]]]:
        """Alle bekannten Stat-Fingerabdruecke, in EINER Query geladen.

        Key ist ``(project_id, normalisierter Pfad)``. Der Wert ist eine LISTE,
        weil derselbe Pfad mehrere Rows tragen kann: aendert sich der Inhalt
        einer Quelle, entsteht eine zweite Row mit neuem ``source_sha256``,
        waehrend die alte Row weiter auf denselben Pfad zeigt. Die Aufloesung
        macht ``_source_sha`` ueber den Stat-Vergleich — nicht diese Funktion.
        """
        if self._source_fingerprints_cache is None:
            cache: dict[tuple[int, str], list[tuple[str, int | None, int | None]]] = {}
            rows = self.session.execute(
                select(
                    ProjectSource.project_id,
                    ProjectSource.current_source_path,
                    ProjectSource.source_sha256,
                    ProjectSource.source_bytes,
                    ProjectSource.source_mtime_ns,
                )
            ).all()
            for project_id, path, sha, size, mtime_ns in rows:
                if project_id is None or not path or not sha:
                    continue
                cache.setdefault((project_id, _normalize_path(path)), []).append(
                    (sha, size, mtime_ns)
                )
            self._source_fingerprints_cache = cache
        return self._source_fingerprints_cache

    def _source_sha(self, project_id: int, source: Path, media_type: str) -> str:
        """Quell-Identitaet — ohne die Datei zu lesen, wenn nichts sich aenderte.

        ``migrate_existing_outputs`` laeuft bei JEDEM Projekt-Open. Vorher wurde
        hier bedingungslos ``compute_source_sha256(..., mode="strict")`` gerufen,
        also die komplette Quelldatei gelesen — an einer realen Projekt-DB
        gemessen 123 Clips / 1,16 GB pro Open.

        Der Kurzschluss greift nur, wenn Groesse UND ``st_mtime_ns`` exakt dem
        entsprechen, was beim letzten echten Hash-Lauf gespeichert wurde. Fehlt
        einer der Werte (Bestandszeile, vor Alembic ``a3b4c5d6e7f8``
        geschrieben), wird regulaer gehasht und der Wert in
        ``_upsert_project_source`` nachgetragen — die DB heilt sich beim ersten
        Open selbst, ohne Backfill-Skript.
        """
        candidates = self._source_fingerprints().get(
            (project_id, _normalize_path(source))
        )
        if candidates:
            try:
                stat = source.stat()
            except OSError:
                stat = None
            if stat is not None:
                treffer = {
                    sha
                    for sha, size, mtime_ns in candidates
                    if size is not None
                    and mtime_ns is not None
                    and size == stat.st_size
                    and mtime_ns == stat.st_mtime_ns
                }
                # Nur bei EINDEUTIGEM Treffer abkuerzen. Mehrere passende Rows
                # zum selben Pfad heissen: derselbe Pfad ist unter
                # verschiedenen ``source_sha256`` registriert — z.B. weil er
                # einmal als Audio und einmal als Video gehasht wurde
                # (``compute_source_sha256`` mischt ``media_type`` in den
                # Hash). ``project_sources`` hat keine media_type-Spalte, mit
                # der man das aufloesen koennte. Dann lieber regulaer hashen
                # als die falsche Identitaet zurueckgeben.
                if len(treffer) == 1:
                    return next(iter(treffer))
        return compute_source_sha256(source, media_type=media_type, mode="strict")

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

        # B-814: Stat-Fingerabdruck mitschreiben, damit der naechste Open
        # abkuerzen kann. Nur bei echter Abweichung zuweisen — gleiches Muster
        # wie ``_upsert_artifact``, das die Row sonst unnoetig dirty markiert.
        try:
            stat = source_path.stat()
        except OSError:
            stat = None
        if stat is not None:
            if row.source_bytes != stat.st_size:
                row.source_bytes = stat.st_size
            if row.source_mtime_ns != stat.st_mtime_ns:
                row.source_mtime_ns = stat.st_mtime_ns
            # Cache mitziehen, damit ein zweiter Treffer im selben Lauf
            # ebenfalls abkuerzt.
            key = (project_id, _normalize_path(source_path))
            entries = self._source_fingerprints().setdefault(key, [])
            entries[:] = [e for e in entries if e[0] != source_sha]
            entries.append((source_sha, stat.st_size, stat.st_mtime_ns))
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
        size = file_path.stat().st_size
        # ``migrate_existing_outputs`` laeuft bei JEDEM Projekt-Open. Vorher
        # wurde hier jedes Artefakt (Proxys, Stems) bedingungslos komplett neu
        # gehasht — im groessten real vorhandenen Projekt 0,65 GB pro Open —
        # und ausserdem jede Row unnoetig dirty markiert (UPDATE-Flut +
        # DB-Busy waehrend des Opens). Unveraenderte Groesse bei bereits
        # gespeichertem Hash => nichts neu lesen, nichts schreiben.
        if row.sha256 is None or row.bytes != size:
            row.bytes = size
            row.sha256 = _file_sha256(file_path)
        return row

    def _progress(self, phase: str, index: int, total: int) -> None:
        if self.progress_callback is not None:
            self.progress_callback(phase, index, total)


def _normalize_path(path: str | Path) -> str:
    """Vergleichsform fuer ``project_sources.current_source_path``.

    ``os.path.normcase`` deckt die Windows-Realitaet ab (Gross/Kleinschreibung
    und ``/`` vs ``\\`` sind dort identisch); auf POSIX ist es die Identitaet.
    Ein Fehlschlag beim Normalisieren ist ungefaehrlich: dann greift der
    Kurzschluss nicht und es wird regulaer gehasht.
    """
    return os.path.normcase(str(path))


def _file_sha256(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
