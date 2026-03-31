import logging
from pathlib import Path

from sqlalchemy.orm import Session

from database import engine, AudioTrack, VideoClip, StructureSegment
from services.vector_db_service import VectorDBService

logger = logging.getLogger(__name__)


def _invalidate_pacing_caches():
    """Pacing-Caches leeren nach Media-Import."""
    try:
        from services.pacing_service import invalidate_pacing_caches
        invalidate_pacing_caches()
    except ImportError:
        pass

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


def ingest_audio(file_path: str, project_id: int = 1) -> AudioTrack | None:
    path = Path(file_path)
    if path.suffix.lower() not in AUDIO_EXTENSIONS:
        raise ValueError(f"Nicht unterstuetzte Audio-Extension: {path.suffix}")
    resolved = str(path.resolve())

    try:
        with Session(engine) as session:
            existing = session.query(AudioTrack).filter_by(file_path=resolved).first()
            if existing:
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
            _invalidate_pacing_caches()
            return track
    except Exception as e:
        logger.error("ingest_audio fehlgeschlagen: %s", e)
        raise


def _probe_video_meta(file_path: str) -> dict:
    """Schnelle ffprobe-Abfrage fuer Video-Metadaten beim Import."""
    import subprocess, json, sys
    try:
        cmd = [
            "ffprobe", "-v", "quiet",
            "-print_format", "json",
            "-show_format", "-show_streams",
            file_path,
        ]
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10,
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
    except Exception as e:
        logger.warning("ffprobe Metadaten-Abfrage fehlgeschlagen für '%s': %s", file_path, e)
        return {}


def ingest_video(file_path: str, project_id: int = 1) -> VideoClip | None:
    path = Path(file_path)
    if path.suffix.lower() not in VIDEO_EXTENSIONS:
        raise ValueError(f"Nicht unterstuetzte Video-Extension: {path.suffix}")
    resolved = str(path.resolve())

    # Bug-15 Fix: ffprobe-Subprocess VOR dem Öffnen der Session aufrufen.
    # Session-Split-Pattern: DB-Session nicht länger als nötig offen halten,
    # insbesondere nicht während externer Subprocess-Aufrufe.
    video_meta = _probe_video_meta(resolved)

    try:
        with Session(engine) as session:
            existing = session.query(VideoClip).filter_by(file_path=resolved).first()
            if existing:
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
            _invalidate_pacing_caches()
            return clip
    except Exception as e:
        logger.error("ingest_video fehlgeschlagen: %s", e)
        raise


def get_audio_detail_data(audio_id: int) -> dict | None:
    """Laedt Audio-Metadaten fuer die Detail-Cards im MEDIA-Workspace."""
    import json as _json
    from services.key_detection_service import CAMELOT_WHEEL
    try:
        with Session(engine) as session:
            track = session.get(AudioTrack, audio_id)
            if not track:
                return None

            beat_count = None
            if track.beatgrid and track.beatgrid.beat_positions:
                try:
                    beat_count = len(_json.loads(track.beatgrid.beat_positions))
                except Exception:
                    pass

            camelot = CAMELOT_WHEEL.get(track.key) if track.key else None
            stems_status = "Ja" if track.stem_vocals_path else "Nein"

            seg_rows = session.query(StructureSegment).filter_by(
                audio_track_id=audio_id
            ).order_by(StructureSegment.start_time).all()
            segments = []
            if seg_rows:
                duration = track.duration or 1.0
                for seg in seg_rows:
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
                "energy": track.energy_curve,
                "genre": track.genre,
                "spectral_centroid": None,
                "lufs": track.lufs,
                "stems_status": stems_status,
                "structure_segments": segments,
            }
    except Exception as e:
        logger.error("get_audio_detail_data(%d) fehlgeschlagen: %s", audio_id, e)
        return None


def get_all_audio(project_id: int = 1, limit: int = 5000) -> list[dict]:
    with Session(engine) as session:
        tracks = session.query(AudioTrack).filter_by(project_id=project_id).limit(limit).all()
        result = []
        for t in tracks:
            # Stem-Status berechnen
            stem_count = sum(1 for p in [
                t.stem_vocals_path, t.stem_drums_path,
                t.stem_bass_path, t.stem_other_path
            ] if p)
            stems = f"{stem_count}/4" if stem_count > 0 else "-"

            result.append({
                "id": t.id, "title": t.title, "file_path": t.file_path,
                "type": "Audio", "bpm": t.bpm, "stems": stems,
            })
        return result


def get_all_video(project_id: int = 1, limit: int = 5000) -> list[dict]:
    with Session(engine) as session:
        clips = session.query(VideoClip).filter_by(project_id=project_id).limit(limit).all()
        result = []
        for c in clips:
            res = f"{c.width}x{c.height}" if c.width and c.height else None
            result.append({
                "id": c.id,
                "title": Path(c.file_path).stem,
                "file_path": c.file_path,
                "type": "Video",
                "resolution": res,
                "fps": c.fps,
                "stems": "-",
            })
        return result


def get_all_media(project_id: int = 1) -> list[dict]:
    return get_all_audio(project_id) + get_all_video(project_id)


def delete_all_media(project_id: int = 1) -> int:
    """Loescht alle Audio- und Video-Eintraege aus der Datenbank.

    Löscht zuerst alle abhängigen Child-Rows (ClipAnchors, TimelineEntries,
    AudioVideoAnchors, Scenes, Beatgrids, WaveformData), dann die Parents.
    HINWEIS: AIPacingMemory wird NIEMALS geloescht – das KI-Gedaechtnis ist permanent.
    """
    from database import (
        AudioVideoAnchor, ClipAnchor, TimelineEntry,
        Scene, Beatgrid, WaveformData, PacingBlueprint,
        StructureSegment, HotCue,
    )
    with Session(engine) as session:
        # IDs der betroffenen Parent-Rows sammeln
        audio_ids = [
            r[0] for r in session.query(AudioTrack.id).filter_by(project_id=project_id).all()
        ]
        video_ids = [
            r[0] for r in session.query(VideoClip.id).filter_by(project_id=project_id).all()
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

        if audio_ids or video_ids:
            session.query(AudioVideoAnchor).filter(
                (AudioVideoAnchor.audio_track_id.in_(audio_ids if audio_ids else [0]))
                | (AudioVideoAnchor.video_clip_id.in_(video_ids if video_ids else [0]))
            ).delete(synchronize_session=False)

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
            # Phase 4: Neue Child-Tabellen von AudioTrack
            session.query(StructureSegment).filter(
                StructureSegment.audio_track_id.in_(audio_ids)
            ).delete(synchronize_session=False)
            session.query(HotCue).filter(
                HotCue.audio_track_id.in_(audio_ids)
            ).delete(synchronize_session=False)

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

        # Jetzt die Parents selbst
        count_a = session.query(AudioTrack).filter_by(project_id=project_id).delete(
            synchronize_session=False
        )
        count_v = session.query(VideoClip).filter_by(project_id=project_id).delete(
            synchronize_session=False
        )
        session.commit()

        # P2-01: VectorDB Cascade-Delete — alle Embeddings loeschen
        try:
            VectorDBService().delete_all()
        except Exception as e:
            logger.warning("VectorDB delete_all fehlgeschlagen: %s", e)

        return count_a + count_v


def delete_selected_media(video_ids: list[int], audio_ids: list[int]) -> int:
    """Loescht einzelne Audio- und Video-Eintraege anhand ihrer IDs.

    Bereinigt zuerst alle abhaengigen Child-Rows (ClipAnchors, TimelineEntries,
    AudioVideoAnchors, Scenes, Beatgrids, WaveformData), dann die Parents.
    AIPacingMemory wird NIEMALS geloescht.
    """
    from database import (
        AudioVideoAnchor, ClipAnchor, TimelineEntry,
        Scene, Beatgrid, WaveformData, StructureSegment, HotCue,
    )
    if not video_ids and not audio_ids:
        return 0

    with Session(engine) as session:
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

        if audio_ids or video_ids:
            session.query(AudioVideoAnchor).filter(
                (AudioVideoAnchor.audio_track_id.in_(audio_ids if audio_ids else [0]))
                | (AudioVideoAnchor.video_clip_id.in_(video_ids if video_ids else [0]))
            ).delete(synchronize_session=False)

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

        # Parents loeschen
        count_a = 0
        count_v = 0
        if audio_ids:
            count_a = session.query(AudioTrack).filter(
                AudioTrack.id.in_(audio_ids)
            ).delete(synchronize_session=False)
        if video_ids:
            count_v = session.query(VideoClip).filter(
                VideoClip.id.in_(video_ids)
            ).delete(synchronize_session=False)

        session.commit()

        # P2-01: VectorDB Cascade-Delete — Embeddings fuer geloeschte VideoClips entfernen
        if video_ids:
            try:
                VectorDBService().delete_by_clip_ids(video_ids)
            except Exception as e:
                logger.warning("VectorDB delete_by_clip_ids fehlgeschlagen: %s", e)

        return count_a + count_v


def import_video_folder(
    folder_path: str,
    project_id: int = 1,
    recursive: bool = True,
) -> list[VideoClip]:
    """Importiert alle Videos aus einem Ordner (rekursiv).

    Phase 6: Batch Video Import.
    Scannt den Ordner nach allen unterstuetzten Video-Dateien und
    importiert jede einzeln via ingest_video().

    Returns: Liste der erfolgreich importierten VideoClip-Objekte.
    """
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
        try:
            clip = ingest_video(str(video_file), project_id=project_id)
            if clip:
                imported.append(clip)
            else:
                skipped += 1
        except Exception as e:
            logger.warning("Import uebersprungen: %s — %s", video_file.name, e)
            skipped += 1

    logger.info("Batch-Import fertig: %d importiert, %d uebersprungen",
                len(imported), skipped)
    _invalidate_pacing_caches()
    return imported
