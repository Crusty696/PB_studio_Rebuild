import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import or_
from sqlalchemy.orm import Session

from database import engine, AudioTrack, VideoClip, StructureSegment
from services.startup_checks import get_ffprobe_bin
from services.timeout_constants import FFMPEG_PROBE_TIMEOUT_SEC
from services.vector_db_service import VectorDBService

logger = logging.getLogger(__name__)


def _resolve_project_id(project_id: int | None) -> int:
    """B-053 Cycle 12: ersetzt hardcoded project_id=1.

    Wenn der Caller None passt, wird das aktive Projekt aus der DB
    aufgelöst. Fallback auf 1 nur wenn kein aktives Projekt existiert
    (z.B. brand-fresh Setup vor erstem create_project).
    """
    if project_id is not None:
        return int(project_id)
    try:
        from database.session import get_active_project_id
        active = get_active_project_id()
        if active is not None:
            return int(active)
    except (ImportError, AttributeError, RuntimeError) as exc:
        logger.warning("_resolve_project_id: get_active_project_id failed: %s", exc)
    logger.warning(
        "ingest_service: kein aktives Projekt — falle auf project_id=1 zurück. "
        "Das kann nach Projekt-Switch zu falschen Zuordnungen führen (B-053)."
    )
    return 1


def _resolve_project_id_for_ingest(project_id: int | None) -> int:
    """B-280: Project-ID-Aufloesung speziell fuer den Import-Pfad.

    Im Gegensatz zu ``_resolve_project_id`` (genutzt von Read-Pfaden, die auf
    einer leeren DB still eine leere Liste liefern duerfen) faellt der Import
    NICHT auf ``project_id=1`` zurueck, wenn kein aktives Projekt existiert.

    Vorher: Bei leerer DB loeste die ``=1``-Fallback-Kette eine irrefuehrende
    FK-Fehlermeldung ("Projekt mit id=1 existiert nicht") pro Datei aus. Jetzt
    bekommt der User eine klare, einmalige "erst Projekt anlegen/oeffnen"-
    Meldung.

    Raises:
        ValueError: Wenn ``project_id is None`` UND kein aktives Projekt in der
            DB existiert.
    """
    if project_id is not None:
        return int(project_id)
    try:
        from database.session import get_active_project_id
        active = get_active_project_id()
    except (ImportError, AttributeError, RuntimeError) as exc:
        logger.warning("_resolve_project_id_for_ingest: get_active_project_id failed: %s", exc)
        active = None
    if active is not None:
        return int(active)
    raise ValueError(
        "Kein aktives Projekt vorhanden. Bitte zuerst ein Projekt anlegen "
        "oder oeffnen, bevor Medien importiert werden."
    )


def _ensure_project_exists(project_id: int) -> None:
    """B-054: Project-FK-Pre-Check vor INSERT.

    SQLite mit WAL kann FK-Violations erst beim Commit melden →
    User sieht generisches "Import fehlgeschlagen" statt klares
    "Projekt {id} existiert nicht". Wir pruefen vorher mit einem
    schnellen SELECT.

    Raises:
        ValueError: Wenn das Projekt nicht (mehr) existiert oder
                    soft-geloescht ist.
    """
    try:
        from database import nullpool_session
        from database.models import Project
    except ImportError as exc:
        # Falls Module nicht ladbar: lass den FK-Check beim Commit feuern.
        logger.warning("B-054: _ensure_project_exists import failed: %s", exc)
        return
    try:
        with nullpool_session() as session:
            proj = (
                session.query(Project)
                .filter(Project.id == project_id, Project.deleted_at.is_(None))
                .first()
            )
            if proj is None:
                raise ValueError(
                    f"Projekt mit id={project_id} existiert nicht "
                    f"(oder ist soft-geloescht). Import abgebrochen."
                )
    except ValueError:
        raise
    except Exception as exc:
        # B-212: OperationalError (DB-Lock) ist KEIN Pre-Check-Fail im
        # gleichen Sinne wie ein fehlendes Projekt — wir muessen den User
        # konkret informieren statt das generische FK-Error vom INSERT
        # spaeter zu kassieren. SQLAlchemy / sqlite3 OperationalError fangen
        # wir ueber den Klassennamen ab (Import zur Vermeidung von
        # zirkulaerem Import bei Service-Bootstrap).
        is_db_lock = exc.__class__.__name__ in ("OperationalError", "DatabaseError")
        if is_db_lock:
            raise ValueError(
                f"DB temporaer nicht verfuegbar (Lock/Busy) — Pre-Check fuer "
                f"project_id={project_id} fehlgeschlagen: {exc}. "
                f"Bitte Vorgang erneut versuchen."
            ) from exc
        # B-054 Original: andere unerwartete Fehler (Schema-Drift, etc.)
        # nicht doppelt crashen lassen — der spaetere INSERT zeigt den
        # konkreten Fehler.
        logger.warning("B-054: _ensure_project_exists query failed: %s", exc)

def _json_loads_safe(value):
    """Parst einen JSON-String zu einer Liste/dict; gibt None zurueck bei Fehler."""
    if value is None:
        return None
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def _invalidate_pacing_caches():
    """Pacing-Caches leeren nach Media-Import."""
    try:
        from services.pacing_service import invalidate_pacing_caches
        invalidate_pacing_caches()
    except ImportError as e:
        logger.warning("Invalidating pacing caches after media import: %s", e)


def _apply_cross_project_reuse_after_ingest(
    session: Session,
    *,
    source_path: Path,
    media_type: str,
    media_id: int,
    project_id: int,
) -> None:
    """Best-effort OTK-021 reuse status; import itself stays authoritative."""
    try:
        from services.storage_provenance.cross_project_reuse import apply_cross_project_reuse_status

        hit = apply_cross_project_reuse_status(
            session,
            source_path,
            media_type=media_type,
            media_id=media_id,
            current_project_id=project_id,
        )
        if hit is not None:
            logger.info(
                "OTK-021 cross-project reuse applied: %s/%d from project=%s steps=%s",
                media_type,
                media_id,
                hit.project_name,
                [step.analysis_step_key for step in hit.steps],
            )
    except Exception as exc:
        logger.warning(
            "OTK-021 cross-project reuse check failed for %s/%d (%s): %s",
            media_type,
            media_id,
            source_path,
            exc,
        )

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".aac", ".m4a", ".wma"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".webm", ".flv", ".m4v"}


def _file_meta(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Datei nicht gefunden: {path}")
    stat = path.stat()
    return {
        "file_path": str(path.resolve()),
        "title": path.stem,
        "size_bytes": stat.st_size,
        "extension": path.suffix.lower(),
    }


def ingest_audio(
    file_path: str, project_id: int | None = None, *, invalidate_caches: bool = True
) -> AudioTrack | None:
    # B-151: Folder-Import-Loops setzen ``invalidate_caches=False`` und
    # rufen am Ende des Batches einmalig _invalidate_pacing_caches() auf
    # — sonst feuert der Cache-Rebuild N+1 mal pro Datei.
    # B-280: kein =1-Fallback bei leerer DB — klare "erst Projekt anlegen"-
    # Fehlermeldung statt irrefuehrendem FK-Error.
    project_id = _resolve_project_id_for_ingest(project_id)
    # B-054: Pre-Check Project-FK damit der User klare Fehlermeldung
    # sieht statt generischer "Import fehlgeschlagen" beim Commit.
    _ensure_project_exists(project_id)
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Audio-Datei nicht gefunden: {file_path}")
    if path.suffix.lower() not in AUDIO_EXTENSIONS:
        raise ValueError(f"Nicht unterstuetzte Audio-Extension: {path.suffix}")
    resolved = str(path.resolve())

    try:
        from database import nullpool_session
        with nullpool_session() as session:
            # F-13 (B-345): scope duplicate check to the project (see ingest_video).
            existing = (
                session.query(AudioTrack)
                .filter_by(project_id=project_id, file_path=resolved)
                .first()
            )
            if existing is not None:
                # B-175: Re-Import nach Soft-Delete. Die UNIQUE-Constraint
                # (project_id, file_path) ist nicht soft-delete-aware — ein
                # erneuter INSERT wuerde am IntegrityError scheitern und ein
                # aktiver Duplikat-Treffer soll weiterhin still uebersprungen
                # werden. Wenn die existierende Zeile soft-geloescht ist,
                # "undeleten" wir sie (deleted_at=None) statt zu skippen.
                if existing.deleted_at is not None:
                    existing.deleted_at = None
                    session.commit()
                    session.refresh(existing)
                    _apply_cross_project_reuse_after_ingest(
                        session,
                        source_path=path,
                        media_type="audio",
                        media_id=existing.id,
                        project_id=project_id,
                    )
                    if invalidate_caches:
                        _invalidate_pacing_caches()
                    return existing
                return None

            meta = _file_meta(path)
            track = AudioTrack(
                project_id=project_id,
                file_path=meta["file_path"],
                title=meta["title"],
            )
            session.add(track)
            session.commit()
            session.refresh(track)
            _apply_cross_project_reuse_after_ingest(
                session,
                source_path=path,
                media_type="audio",
                media_id=track.id,
                project_id=project_id,
            )
            if invalidate_caches:
                _invalidate_pacing_caches()
            return track
    except Exception as e:  # broad catch intentional — re-raised after logging; SQLAlchemy + OS errors
        logger.error("ingest_audio fehlgeschlagen: %s", e)
        raise


def _probe_video_meta(file_path: str) -> dict:
    """Schnelle ffprobe-Abfrage fuer Video-Metadaten beim Import."""
    try:
        cmd = [
            get_ffprobe_bin(), "-v", "quiet",
            "-print_format", "json",
            "-show_format", "-show_streams",
            file_path,
        ]
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=FFMPEG_PROBE_TIMEOUT_SEC,
                                encoding="utf-8", errors="replace", **kwargs)
        if result.returncode != 0:
            return {}
        data = json.loads(result.stdout)
        video_stream = next(
            (s for s in data.get("streams", []) if s.get("codec_type") == "video"), None
        )
        if not video_stream:
            return {}
        fps_str = video_stream.get("r_frame_rate", "30/1")
        num, den = fps_str.split("/") if "/" in fps_str else (fps_str, "1")
        fps = round(float(num) / float(den), 2) if float(den) > 0 else 30.0
        return {
            "duration": float(data.get("format", {}).get("duration", 0)),
            "width": int(video_stream.get("width", 0)),
            "height": int(video_stream.get("height", 0)),
            "fps": fps,
            "codec": video_stream.get("codec_name", ""),
        }
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError, ValueError) as e:
        logger.warning("ffprobe Metadaten-Abfrage fehlgeschlagen für '%s': %s", file_path, e)
        return {}


def ingest_video(
    file_path: str, project_id: int | None = None, *, invalidate_caches: bool = True
) -> VideoClip | None:
    # B-151: Folder-Import-Loops setzen ``invalidate_caches=False`` und
    # rufen am Ende des Batches einmalig _invalidate_pacing_caches() auf.
    # B-280: kein =1-Fallback bei leerer DB (siehe ingest_audio).
    project_id = _resolve_project_id_for_ingest(project_id)
    # B-054: Pre-Check Project-FK (siehe ingest_audio).
    _ensure_project_exists(project_id)
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Video-Datei nicht gefunden: {file_path}")
    if path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError(f"Nicht unterstuetzte Video-Extension: {path.suffix}")
    resolved = str(path.resolve())

    # Bug-15 Fix: ffprobe-Subprocess VOR dem Öffnen der Session aufrufen.
    # Session-Split-Pattern: DB-Session nicht länger als nötig offen halten,
    # insbesondere nicht während externer Subprocess-Aufrufe.
    video_meta = _probe_video_meta(resolved)

    try:
        from database import nullpool_session
        with nullpool_session() as session:
            # F-13 (B-345): scope the duplicate check to the project. The unique
            # constraint is (project_id, file_path), so the same file may live in
            # two projects; a project-agnostic check wrongly refused to import it
            # into a second project.
            existing = (
                session.query(VideoClip)
                .filter_by(project_id=project_id, file_path=resolved)
                .first()
            )
            if existing is not None:
                # B-175: Re-Import nach Soft-Delete (siehe ingest_audio).
                # Soft-geloeschte Zeile undeleten statt am IntegrityError der
                # nicht-soft-delete-awaren UNIQUE-Constraint zu scheitern.
                if existing.deleted_at is not None:
                    existing.deleted_at = None
                    session.commit()
                    session.refresh(existing)
                    _apply_cross_project_reuse_after_ingest(
                        session,
                        source_path=path,
                        media_type="video",
                        media_id=existing.id,
                        project_id=project_id,
                    )
                    if invalidate_caches:
                        _invalidate_pacing_caches()
                    return existing
                return None

            meta = _file_meta(path)
            clip = VideoClip(
                project_id=project_id,
                file_path=meta["file_path"],
                duration=video_meta.get("duration"),
                width=video_meta.get("width"),
                height=video_meta.get("height"),
                fps=video_meta.get("fps"),
                codec=video_meta.get("codec"),
            )
            session.add(clip)
            session.commit()
            session.refresh(clip)
            _apply_cross_project_reuse_after_ingest(
                session,
                source_path=path,
                media_type="video",
                media_id=clip.id,
                project_id=project_id,
            )
            if invalidate_caches:
                _invalidate_pacing_caches()
            return clip
    except Exception as e:  # broad catch intentional — re-raised after logging; SQLAlchemy + OS errors
        logger.error("ingest_video fehlgeschlagen: %s", e)
        raise


def get_audio_detail_data(audio_id: int) -> dict | None:
    """Laedt Audio-Metadaten fuer die Detail-Cards im MEDIA-Workspace."""
    from services.key_detection_service import CAMELOT_WHEEL
    try:
        with Session(engine) as session:
            track = session.get(AudioTrack, audio_id)
            if not track:
                return None

            beat_count = None
            if track.beatgrid and track.beatgrid.beat_positions:
                try:
                    # C-3 FIX: SQLAlchemy auto-deserializes JSON columns — no manual json.loads() needed
                    beat_count = len(track.beatgrid.beat_positions)
                except (TypeError, AttributeError) as e:
                    logger.warning("beat_positions length fehlgeschlagen (audio_id=%d): %s", audio_id, e)

            camelot = CAMELOT_WHEEL.get(track.key) if track.key else None
            stems_status = "Ja" if track.stem_vocals_path else "Nein"

            seg_rows = session.query(StructureSegment).filter_by(
                audio_track_id=audio_id
            ).order_by(StructureSegment.start_time).all()
            segments = []
            if seg_rows:
                duration = track.duration or 1.0
                for seg in seg_rows:
                    # FIX H-16: Guard against None start_time/end_time to prevent TypeError
                    if seg.start_time is None or seg.end_time is None:
                        continue
                    segments.append({
                        "label": seg.label,
                        "start": seg.start_time / duration,
                        "end": seg.end_time / duration,
                    })

            return {
                "bpm": track.bpm,
                "beat_count": beat_count,
                "bpm_confidence": None,
                "key": track.key,
                "key_confidence": track.key_confidence,
                "camelot": camelot,
                "mood": track.mood,
                "energy": _json_loads_safe(track.energy_curve),  # BUG-015: war JSON-String statt Liste
                "genre": track.genre,
                "spectral_centroid": None,
                "lufs": track.lufs,
                "stems_status": stems_status,
                "structure_segments": segments,
            }
    except Exception as e:  # broad catch intentional — SQLAlchemy query + JSON parse can raise many types
        logger.error("get_audio_detail_data(%d) fehlgeschlagen: %s", audio_id, e)
        return None


def get_all_audio(project_id: int | None = None, limit: int | None = None) -> list[dict]:
    """Liefert ALLE Audio-Tracks des Projekts.

    B-055: kein stiller 5000-Cap mehr — Default `limit=None` liefert die
    komplette Sammlung. B-053 Cycle 12: project_id=None löst auf das
    aktive Projekt auf, kein hardcoded =1 mehr.
    """
    project_id = _resolve_project_id(project_id)
    from services import analysis_status_service
    # Collect ORM data first, then close session before calling analysis_status_service
    # to avoid connection pool exhaustion (selectin loaders hold pool connections).
    with Session(engine) as session:
        # H-4 FIX: Filter out soft-deleted tracks (deleted_at is None)
        q = session.query(AudioTrack).filter_by(
            project_id=project_id
        ).filter(
            AudioTrack.deleted_at.is_(None)
        )
        if limit is not None:
            q = q.limit(limit)
        tracks = q.all()
        if len(tracks) > 5000:
            logger.info(
                "get_all_audio: %d Tracks geladen (große Sammlung). "
                "Erwäge explizite Pagination falls die UI-Latenz zu hoch ist.",
                len(tracks),
            )
        raw_data = []
        for t in tracks:
            stem_count = sum(1 for p in [
                t.stem_vocals_path, t.stem_drums_path,
                t.stem_bass_path, t.stem_other_path
            ] if p)
            raw_data.append({
                "id": t.id, "title": t.title, "file_path": t.file_path,
                "type": "Audio", "bpm": t.bpm,
                "stems": f"{stem_count}/4" if stem_count > 0 else "-",
                "key": t.key,
                "mood": t.mood,
                "genre": t.genre,
                "duration": t.duration,
                "energy_curve": t.energy_curve,
            })

    # Session is closed — safe to call analysis_status_service (opens its own session)
    for item in raw_data:
        try:
            item["analysis_percent"] = analysis_status_service.get_completion_percent("audio", item["id"])
        except Exception:
            item["analysis_percent"] = 0

    return raw_data


def get_all_video(project_id: int | None = None, limit: int | None = None) -> list[dict]:
    """Liefert ALLE Video-Clips des Projekts. B-055/B-053 Cycle 12."""
    project_id = _resolve_project_id(project_id)
    from services import analysis_status_service
    # Collect ORM data first, then close session before calling analysis_status_service
    # to avoid connection pool exhaustion (selectin loaders hold pool connections).
    with Session(engine) as session:
        q = session.query(VideoClip).filter(
            VideoClip.project_id == project_id,
            VideoClip.deleted_at.is_(None)
        )
        if limit is not None:
            q = q.limit(limit)
        clips = q.all()
        if len(clips) > 5000:
            logger.info(
                "get_all_video: %d Clips geladen (große Sammlung).",
                len(clips),
            )
        raw_data = []
        for c in clips:
            raw_data.append({
                "id": c.id,
                "title": Path(c.file_path).stem,
                "file_path": c.file_path,
                "type": "Video",
                "resolution": f"{c.width}x{c.height}" if c.width and c.height else None,
                "fps": c.fps,
                "codec": getattr(c, "codec", None) or "-",
                "stems": "-",
            })

    # Session is closed — safe to call analysis_status_service (opens its own session)
    for item in raw_data:
        try:
            item["analysis_percent"] = analysis_status_service.get_completion_percent("video", item["id"])
        except Exception:
            item["analysis_percent"] = 0

    return raw_data


def get_all_media(project_id: int | None = None) -> list[dict]:
    project_id = _resolve_project_id(project_id)
    return get_all_audio(project_id) + get_all_video(project_id)


def get_combo_items(project_id: int | None = None) -> list[dict]:
    """Lightweight Variante von get_all_media() — **NUR** fuer Director-Combos.

    P8-FREEZE-FIX: Vorher nutzten die Audio-/Video-Combos `get_all_media()`,
    das fuer jeden Audio-Track das riesige `energy_curve` JSON-Blob laedt
    (MB-Groesse bei langen Tracks) und pro Item einen extra
    `analysis_status_service.get_completion_percent()`-Call macht (N+1).
    Beim App-Boot blockierte das den Main-Thread mehrere Sekunden.

    Diese Funktion liefert nur leichte Spalten fuer Labels und Default-
    Auswahl. Keine grossen JSON-Blobs, kein N+1 Status-Call.
    """
    project_id = _resolve_project_id(project_id)
    items: list[dict] = []
    with Session(engine) as session:
        audios = session.query(
            AudioTrack.id, AudioTrack.title, AudioTrack.bpm, AudioTrack.key, AudioTrack.lufs,
        ).filter_by(project_id=project_id).filter(
            AudioTrack.deleted_at.is_(None)
        ).order_by(AudioTrack.id).all()
        for aid, title, bpm, key, lufs in audios:
            items.append({
                "id": aid,
                "title": title,
                "bpm": bpm,
                "key": key,
                "lufs": lufs,
                "type": "Audio",
            })

        videos = session.query(
            VideoClip.id, VideoClip.file_path,
        ).filter(
            VideoClip.project_id == project_id,
            VideoClip.deleted_at.is_(None),
        ).order_by(VideoClip.id).all()
        for vid, path in videos:
            items.append({"id": vid, "title": Path(path).stem, "type": "Video"})
    return items


def delete_all_media(project_id: int | None = None) -> int:
    """Loescht alle Audio- und Video-Eintraege aus der Datenbank.

    Löscht zuerst alle abhängigen Child-Rows (ClipAnchors, TimelineEntries,
    AudioVideoAnchors, Scenes, Beatgrids, WaveformData), dann die Parents.
    HINWEIS: AIPacingMemory wird NIEMALS geloescht – das KI-Gedaechtnis ist permanent.
    B-053 Cycle 12: project_id=None löst auf das aktive Projekt auf.
    B-439: Destruktiver Pfad nutzt den raise-Resolver (wie der Import) statt des
    =1-Fallbacks. Bei project_id=None ohne aktives Projekt wird ValueError
    geworfen statt versehentlich Medien von project_id=1 zu loeschen.
    """
    project_id = _resolve_project_id_for_ingest(project_id)
    # B-462 Stage 1 (D-056): analysis children (Scene/Beatgrid/...) are no longer
    # deleted here; only relationship children (anchors/timeline/blueprint).
    from database import (
        AudioVideoAnchor, ClipAnchor, TimelineEntry, PacingBlueprint,
    )
    from database import nullpool_session
    with nullpool_session() as session:
        # IDs der betroffenen Parent-Rows sammeln
        # H-8 FIX: Filter out soft-deleted items (deleted_at is None)
        audio_ids = [
            r[0] for r in session.query(AudioTrack.id).filter_by(
                project_id=project_id
            ).filter(AudioTrack.deleted_at.is_(None)).all()
        ]
        video_ids = [
            r[0] for r in session.query(VideoClip.id).filter_by(
                project_id=project_id
            ).filter(VideoClip.deleted_at.is_(None)).all()
        ]
        timeline_ids = [
            r[0] for r in session.query(TimelineEntry.id).filter_by(project_id=project_id).all()
        ]

        # Grandchildren zuerst
        if timeline_ids:
            session.query(ClipAnchor).filter(
                ClipAnchor.timeline_entry_id.in_(timeline_ids)
            ).delete(synchronize_session=False)

        # Children
        if timeline_ids:
            session.query(TimelineEntry).filter(
                TimelineEntry.id.in_(timeline_ids)
            ).delete(synchronize_session=False)

        # B-153: konditional bauen statt ``[0]``-Sentinel — IN(0) matched
        # eine reale Row mit id=0 (kann durch Test-Fixture / Manual-Seed
        # entstehen, SQLite startet zwar autoincrement bei 1, aber das ist
        # kein Constraint).
        anchor_conds = []
        if audio_ids:
            anchor_conds.append(AudioVideoAnchor.audio_track_id.in_(audio_ids))
        if video_ids:
            anchor_conds.append(AudioVideoAnchor.video_clip_id.in_(video_ids))
        if anchor_conds:
            session.query(AudioVideoAnchor).filter(
                or_(*anchor_conds)
            ).delete(synchronize_session=False)

        # B-462 Stage 1 (D-056): analysis children (Scene/Beatgrid/WaveformData/
        # StructureSegment/HotCue) are KEPT on soft delete for full undo; they are
        # filtered via the soft-deleted parent on read paths.

        # PacingBlueprints (direct child of Project, but media-related)
        session.query(PacingBlueprint).filter_by(project_id=project_id).delete(
            synchronize_session=False
        )

        # ===== WARNUNG: AIPacingMemory darf NIE geloescht werden! =====
        # Das KI-Langzeitgedaechtnis (Tabelle 'ai_pacing_memory') ist projektuebergreifend
        # und enthaelt gelernte Schnitt-Entscheidungen des Users. Ein Reset darf NUR
        # Videos, Audios, Stems und Timelines loeschen – NIEMALS das KI-Gedaechtnis!
        # Zukuenftige Agenten: Fuege hier KEINEN Delete auf AIPacingMemory hinzu.
        # ================================================================

        # B-462 Stage 1 (D-056): soft-delete the parents (set deleted_at) instead of
        # a physical delete. Only currently-active rows (deleted_at IS NULL) are
        # affected and counted.
        _now = datetime.now()
        count_a = session.query(AudioTrack).filter_by(
            project_id=project_id
        ).filter(AudioTrack.deleted_at.is_(None)).update(
            {AudioTrack.deleted_at: _now}, synchronize_session=False
        )
        count_v = session.query(VideoClip).filter_by(
            project_id=project_id
        ).filter(VideoClip.deleted_at.is_(None)).update(
            {VideoClip.deleted_at: _now}, synchronize_session=False
        )

        # B-139 / B-462 Stage 1 (D-056): VectorDB-Cleanup VOR dem SQL-Commit. Auch
        # bei Soft-Delete werden die Embeddings entfernt, damit Semantic-Search keine
        # soft-deleted Clips findet (die VectorDB kennt deleted_at nicht). Schlaegt
        # die VectorDB fehl, rollback der Soft-Delete-Updates — kein partial state.
        try:
            VectorDBService().delete_all()
        except (RuntimeError, OSError, ImportError) as e:
            logger.error(
                "VectorDB delete_all fehlgeschlagen — Soft-Delete rolled back "
                "um Orphan-Embeddings zu vermeiden. Bitte VectorDB pruefen und "
                "Reset wiederholen. Fehler: %s", e
            )
            session.rollback()
            raise RuntimeError(
                f"Reset abgebrochen: VectorDB konnte nicht geleert werden ({e}). "
                "Soft-Delete wurde NICHT angewendet um Orphan-Embeddings zu vermeiden."
            ) from e

        session.commit()

        return count_a + count_v


def delete_selected_media(video_ids: list[int], audio_ids: list[int]) -> int:
    """Loescht einzelne Audio- und Video-Eintraege anhand ihrer IDs.

    Bereinigt zuerst alle abhaengigen Child-Rows (ClipAnchors, TimelineEntries,
    AudioVideoAnchors, Scenes, Beatgrids, WaveformData), dann die Parents.
    AIPacingMemory wird NIEMALS geloescht.
    """
    # B-462 Stage 1 (D-056): analysis children kept on soft delete; only
    # relationship children (anchors/timeline) are removed here.
    from database import (
        AudioVideoAnchor, ClipAnchor, TimelineEntry,
        nullpool_session,
    )
    if not video_ids and not audio_ids:
        return 0

    # BUG-006: nullpool_session vermeidet Connection-Leaks in Worker-Threads
    with nullpool_session() as session:
        # Timeline-Entries fuer diese Medien finden
        timeline_ids = []
        if audio_ids:
            timeline_ids += [
                r[0] for r in session.query(TimelineEntry.id).filter(
                    TimelineEntry.media_id.in_(audio_ids),
                    TimelineEntry.track == "audio",
                ).all()
            ]
        if video_ids:
            timeline_ids += [
                r[0] for r in session.query(TimelineEntry.id).filter(
                    TimelineEntry.media_id.in_(video_ids),
                    TimelineEntry.track == "video",
                ).all()
            ]

        # Grandchildren zuerst
        if timeline_ids:
            session.query(ClipAnchor).filter(
                ClipAnchor.timeline_entry_id.in_(timeline_ids)
            ).delete(synchronize_session=False)

        # Children
        if timeline_ids:
            session.query(TimelineEntry).filter(
                TimelineEntry.id.in_(timeline_ids)
            ).delete(synchronize_session=False)

        # B-153: konditional bauen statt ``[0]``-Sentinel.
        anchor_conds = []
        if audio_ids:
            anchor_conds.append(AudioVideoAnchor.audio_track_id.in_(audio_ids))
        if video_ids:
            anchor_conds.append(AudioVideoAnchor.video_clip_id.in_(video_ids))
        if anchor_conds:
            session.query(AudioVideoAnchor).filter(
                or_(*anchor_conds)
            ).delete(synchronize_session=False)

        # B-462 Stage 1 (D-056): analysis children (Scene/Beatgrid/WaveformData/
        # StructureSegment/HotCue) are KEPT on soft delete; filtered via parent.

        # B-462 Stage 1 (D-056): soft-delete parents (set deleted_at) instead of
        # physical delete. Only currently-active rows are affected and counted.
        _now = datetime.now()
        count_a = 0
        count_v = 0
        if audio_ids:
            count_a = session.query(AudioTrack).filter(
                AudioTrack.id.in_(audio_ids)
            ).filter(AudioTrack.deleted_at.is_(None)).update(
                {AudioTrack.deleted_at: _now}, synchronize_session=False
            )
        if video_ids:
            count_v = session.query(VideoClip).filter(
                VideoClip.id.in_(video_ids)
            ).filter(VideoClip.deleted_at.is_(None)).update(
                {VideoClip.deleted_at: _now}, synchronize_session=False
            )

        # B-350 / B-462 Stage 1 (D-056): VectorDB-Cleanup VOR SQL-Commit. Auch bei
        # Soft-Delete werden die Embeddings der betroffenen Clips entfernt, damit
        # Semantic-Search keine soft-deleted Clips findet. Schlaegt die VectorDB
        # fehl, rollback der Soft-Delete-Updates — kein partial state.
        if video_ids:
            try:
                VectorDBService().delete_by_clip_ids(video_ids)
            except (RuntimeError, OSError, ImportError) as e:
                logger.error(
                    "VectorDB delete_by_clip_ids fehlgeschlagen — Soft-Delete "
                    "rolled back um Orphan-Embeddings zu vermeiden. Fehler: %s",
                    e,
                )
                session.rollback()
                raise RuntimeError(
                    "Loeschen abgebrochen: VectorDB konnte Embeddings nicht "
                    f"loeschen ({e}). Soft-Delete wurde NICHT angewendet."
                ) from e

        session.commit()

        return count_a + count_v


def get_soft_deleted_media(project_id: int | None = None) -> list[dict]:
    """Listet soft-geloeschte Medien (der "Papierkorb") eines Projekts.

    B-462 Stage 2 (Task 12, option C): Gibt alle Parents mit gesetztem
    ``deleted_at`` zurueck — die Gegenstuecke zu ``get_all_video`` /
    ``get_all_audio``, die soft-deleted Rows ausblenden. Read-Pfad nutzt den
    Read-Resolver (kein raise) wie die anderen Listen-Funktionen.
    """
    project_id = _resolve_project_id(project_id)
    from database import nullpool_session
    items: list[dict] = []
    with nullpool_session() as session:
        videos = session.query(
            VideoClip.id, VideoClip.file_path, VideoClip.deleted_at,
        ).filter(
            VideoClip.project_id == project_id,
            VideoClip.deleted_at.isnot(None),
        ).order_by(VideoClip.deleted_at.desc(), VideoClip.id).all()
        for vid, path, deleted_at in videos:
            items.append({
                "id": vid,
                "title": Path(path).stem,
                "type": "Video",
                "deleted_at": deleted_at,
            })

        audios = session.query(
            AudioTrack.id, AudioTrack.title, AudioTrack.file_path,
            AudioTrack.deleted_at,
        ).filter(
            AudioTrack.project_id == project_id,
            AudioTrack.deleted_at.isnot(None),
        ).order_by(AudioTrack.deleted_at.desc(), AudioTrack.id).all()
        for aid, title, path, deleted_at in audios:
            items.append({
                "id": aid,
                "title": title or Path(path).stem,
                "type": "Audio",
                "deleted_at": deleted_at,
            })
    return items


def restore_media(video_ids: list[int], audio_ids: list[int]) -> int:
    """Stellt soft-geloeschte Medien wieder her (``deleted_at`` zuruecksetzen).

    B-462 Stage 2 (Task 12, option C): Setzt ``deleted_at = NULL`` auf den
    angegebenen, aktuell soft-geloeschten Parents. Analyse-Children
    (Scene/Beatgrid/...) ueberleben den Soft-Delete (Stage 1), darum kehrt der
    Clip mit ihnen zurueck. HINWEIS: VectorDB-Embeddings werden beim Soft-Delete
    entfernt und durch ein Restore NICHT wiederhergestellt — fuer Semantic-Search
    muss der Clip neu analysiert werden.
    """
    if not video_ids and not audio_ids:
        return 0
    from database import nullpool_session
    count = 0
    with nullpool_session() as session:
        if video_ids:
            count += session.query(VideoClip).filter(
                VideoClip.id.in_(video_ids)
            ).filter(VideoClip.deleted_at.isnot(None)).update(
                {VideoClip.deleted_at: None}, synchronize_session=False
            )
        if audio_ids:
            count += session.query(AudioTrack).filter(
                AudioTrack.id.in_(audio_ids)
            ).filter(AudioTrack.deleted_at.isnot(None)).update(
                {AudioTrack.deleted_at: None}, synchronize_session=False
            )
        session.commit()
    return count


def purge_soft_deleted_media(project_id: int | None = None) -> int:
    """Loescht ALLE soft-geloeschten Medien eines Projekts endgueltig ("Papierkorb leeren").

    B-462 Stage 2 (Task 12, option C): Irreversibler physischer Delete der
    soft-geloeschten Parents (``deleted_at IS NOT NULL``) inklusive ihrer
    Analyse-Children (Scene/Beatgrid/WaveformData/StructureSegment/HotCue) und der
    zugehoerigen VectorDB-Embeddings. Recycelt die alte Hard-Delete-Logik, jetzt
    aber strikt auf soft-geloeschte Rows beschraenkt — aktive Medien
    (``deleted_at IS NULL``) bleiben unangetastet. Relationship-Children
    (Timeline/Anchors) wurden bereits beim Soft-Delete entfernt; sie werden hier
    defensiv erneut bereinigt. AIPacingMemory wird NIEMALS geloescht.

    B-439: Nutzt den raise-Resolver — ohne aktives Projekt ValueError statt
    versehentlichem Purge von project_id=1.
    """
    project_id = _resolve_project_id_for_ingest(project_id)
    from database import (
        AudioVideoAnchor, ClipAnchor, TimelineEntry,
        Scene, Beatgrid, WaveformData, StructureSegment, HotCue,
        AnalysisStatus,
        nullpool_session as _nps,
    )
    with _nps() as session:
        audio_ids = [
            r[0] for r in session.query(AudioTrack.id).filter_by(
                project_id=project_id
            ).filter(AudioTrack.deleted_at.isnot(None)).all()
        ]
        video_ids = [
            r[0] for r in session.query(VideoClip.id).filter_by(
                project_id=project_id
            ).filter(VideoClip.deleted_at.isnot(None)).all()
        ]
        if not audio_ids and not video_ids:
            return 0

        # Relationship-Children defensiv (i.d.R. schon beim Soft-Delete weg).
        # B-153: konditional bauen statt [0]-Sentinel.
        if video_ids:
            timeline_ids = [
                r[0] for r in session.query(TimelineEntry.id).filter(
                    TimelineEntry.media_id.in_(video_ids),
                    TimelineEntry.track == "video",
                ).all()
            ]
        else:
            timeline_ids = []
        if audio_ids:
            timeline_ids += [
                r[0] for r in session.query(TimelineEntry.id).filter(
                    TimelineEntry.media_id.in_(audio_ids),
                    TimelineEntry.track == "audio",
                ).all()
            ]
        if timeline_ids:
            session.query(ClipAnchor).filter(
                ClipAnchor.timeline_entry_id.in_(timeline_ids)
            ).delete(synchronize_session=False)
            session.query(TimelineEntry).filter(
                TimelineEntry.id.in_(timeline_ids)
            ).delete(synchronize_session=False)

        anchor_conds = []
        if audio_ids:
            anchor_conds.append(AudioVideoAnchor.audio_track_id.in_(audio_ids))
        if video_ids:
            anchor_conds.append(AudioVideoAnchor.video_clip_id.in_(video_ids))
        if anchor_conds:
            session.query(AudioVideoAnchor).filter(
                or_(*anchor_conds)
            ).delete(synchronize_session=False)

        # Analyse-Children physisch (recycelte Hard-Delete-Logik).
        if video_ids:
            session.query(Scene).filter(
                Scene.video_clip_id.in_(video_ids)
            ).delete(synchronize_session=False)
        if audio_ids:
            session.query(Beatgrid).filter(
                Beatgrid.audio_track_id.in_(audio_ids)
            ).delete(synchronize_session=False)
            session.query(WaveformData).filter(
                WaveformData.audio_track_id.in_(audio_ids)
            ).delete(synchronize_session=False)
            session.query(StructureSegment).filter(
                StructureSegment.audio_track_id.in_(audio_ids)
            ).delete(synchronize_session=False)
            session.query(HotCue).filter(
                HotCue.audio_track_id.in_(audio_ids)
            ).delete(synchronize_session=False)

        # B-188/D-028: ``analysis_status`` ist ein polymorpher Pointer ohne SQL-FK,
        # bleibt bei reinem Parent-Delete als Orphan zurueck. Beim endgueltigen
        # Purge werden die zugehoerigen Status-Rows mitentfernt (Soft-Delete behaelt
        # sie fuer Restore — hier nicht).
        if video_ids:
            session.query(AnalysisStatus).filter(
                AnalysisStatus.media_type == "video",
                AnalysisStatus.media_id.in_(video_ids),
            ).delete(synchronize_session=False)
        if audio_ids:
            session.query(AnalysisStatus).filter(
                AnalysisStatus.media_type == "audio",
                AnalysisStatus.media_id.in_(audio_ids),
            ).delete(synchronize_session=False)

        # ===== WARNUNG: AIPacingMemory darf NIE geloescht werden! =====
        # KI-Langzeitgedaechtnis ist projektuebergreifend — kein Delete hier.
        # ================================================================

        count_a = session.query(AudioTrack).filter(
            AudioTrack.id.in_(audio_ids)
        ).delete(synchronize_session=False) if audio_ids else 0
        count_v = session.query(VideoClip).filter(
            VideoClip.id.in_(video_ids)
        ).delete(synchronize_session=False) if video_ids else 0

        # VectorDB-Cleanup VOR dem Commit. Schlaegt sie fehl, rollback —
        # kein partial state, keine Orphan-Embeddings.
        if video_ids:
            try:
                VectorDBService().delete_by_clip_ids(video_ids)
            except (RuntimeError, OSError, ImportError) as e:
                logger.error(
                    "VectorDB delete_by_clip_ids fehlgeschlagen — Purge rolled "
                    "back um Orphan-Embeddings zu vermeiden. Fehler: %s", e,
                )
                session.rollback()
                raise RuntimeError(
                    "Endgueltiges Loeschen abgebrochen: VectorDB konnte "
                    f"Embeddings nicht loeschen ({e}). Purge wurde NICHT angewendet."
                ) from e

        session.commit()

        return count_a + count_v


def import_video_folder(
    folder_path: str,
    project_id: int | None = None,
    recursive: bool = True,
) -> list[VideoClip]:
    """Importiert alle Videos aus einem Ordner (rekursiv).

    Phase 6: Batch Video Import. B-053 Cycle 12: project_id=None löst
    auf das aktive Projekt auf.

    B-280: kein =1-Fallback bei leerer DB — ohne aktives Projekt schlaegt
    der Import mit klarer "erst Projekt anlegen/oeffnen"-Meldung fehl statt
    mit einem irrefuehrenden FK-Fehler pro Datei.

    Returns: Liste der erfolgreich importierten VideoClip-Objekte.
    """
    project_id = _resolve_project_id_for_ingest(project_id)
    folder = Path(folder_path)
    if not folder.is_dir():
        raise ValueError(f"Ordner existiert nicht: {folder_path}")

    # Alle Video-Dateien sammeln
    pattern = "**/*" if recursive else "*"
    video_files = [
        f for f in folder.glob(pattern)
        if f.is_file() and f.suffix.lower() in VIDEO_EXTENSIONS
    ]

    if not video_files:
        logger.warning("Keine Videos gefunden in: %s", folder_path)
        return []

    logger.info("Batch-Import: %d Videos gefunden in %s", len(video_files), folder_path)

    imported: list[VideoClip] = []
    skipped = 0
    for video_file in sorted(video_files):
        if not video_file.exists():
            logger.warning("Datei nicht mehr vorhanden, uebersprungen: %s", video_file)
            skipped += 1
            continue
        # L-4 FIX: Extension check removed - already filtered by glob above
        try:
            clip = ingest_video(str(video_file), project_id=project_id)
            if clip:
                imported.append(clip)
            else:
                skipped += 1
        except (FileNotFoundError, ValueError, OSError) as e:
            logger.warning("Import uebersprungen: %s — %s", video_file.name, e)
            skipped += 1
        except (IOError, RuntimeError) as e:
            logger.error("Unerwarteter Fehler bei Import von %s: %s", video_file.name, e)
            skipped += 1
        # B-140 Fix: Sicherheitsnetz fuer Custom-Exceptions (z.B. FFmpegError,
        # Subprocess-Errors) die nicht von OSError/IOError/RuntimeError erben.
        # Vorher: Batch brach bei Datei N ab, N-1 waren commited; UI zeigte
        # ungeklaerten "Folder import failed". Jetzt: Skip + log + weiter.
        except Exception as e:  # broad catch intentional — Batch-Recovery
            logger.error("Custom Import-Fehler bei %s — uebersprungen: %s",
                         video_file.name, e, exc_info=True)
            skipped += 1

    logger.info("Batch-Import fertig: %d importiert, %d uebersprungen",
                len(imported), skipped)
    _invalidate_pacing_caches()
    return imported
