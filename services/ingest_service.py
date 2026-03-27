import logging
from pathlib import Path

from sqlalchemy.orm import Session

from database import engine, AudioTrack, VideoClip

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


def get_all_audio(project_id: int = 1) -> list[dict]:
    with Session(engine) as session:
        tracks = session.query(AudioTrack).filter_by(project_id=project_id).all()
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


def get_all_video(project_id: int = 1) -> list[dict]:
    with Session(engine) as session:
        clips = session.query(VideoClip).filter_by(project_id=project_id).all()
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
        return count_a + count_v
