from pathlib import Path

from sqlalchemy.orm import Session

from database import engine, AudioTrack, VideoClip

AUDIO_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".aac", ".m4a", ".wma"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".webm", ".flv", ".m4v"}


def _file_meta(path: Path) -> dict:
    """Liest Basis-Metadaten einer Datei (Größe, Endung)."""
    stat = path.stat()
    return {
        "file_path": str(path.resolve()),
        "title": path.stem,
        "size_bytes": stat.st_size,
        "extension": path.suffix.lower(),
    }


def ingest_audio(file_path: str, project_id: int = 1) -> AudioTrack | None:
    """Importiert eine Audiodatei in die Datenbank. Gibt None zurück bei Duplikat."""
    path = Path(file_path)
    resolved = str(path.resolve())

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
        return track


def ingest_video(file_path: str, project_id: int = 1) -> VideoClip | None:
    """Importiert eine Videodatei in die Datenbank. Gibt None zurück bei Duplikat."""
    path = Path(file_path)
    resolved = str(path.resolve())

    with Session(engine) as session:
        existing = session.query(VideoClip).filter_by(file_path=resolved).first()
        if existing:
            return None

        meta = _file_meta(path)
        clip = VideoClip(
            project_id=project_id,
            file_path=meta["file_path"],
        )
        session.add(clip)
        session.commit()
        session.refresh(clip)
        return clip


def get_all_audio(project_id: int = 1) -> list[dict]:
    """Gibt alle Audiotracks als dict-Liste zurück."""
    with Session(engine) as session:
        tracks = session.query(AudioTrack).filter_by(project_id=project_id).all()
        return [
            {"id": t.id, "title": t.title, "file_path": t.file_path, "type": "Audio", "bpm": t.bpm}
            for t in tracks
        ]


def get_all_video(project_id: int = 1) -> list[dict]:
    """Gibt alle Videoclips als dict-Liste zurück."""
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
            })
        return result


def get_all_media(project_id: int = 1) -> list[dict]:
    """Gibt alle importierten Medien (Audio + Video) zurück."""
    return get_all_audio(project_id) + get_all_video(project_id)
