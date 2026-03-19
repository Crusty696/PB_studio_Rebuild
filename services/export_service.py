"""Export-Service: Fügt Timeline-Clips via FFmpeg zu einem finalen Video zusammen."""

import subprocess
import tempfile
from pathlib import Path

from sqlalchemy.orm import Session
from database import engine, TimelineEntry, AudioTrack, VideoClip

EXPORT_DIR = Path("exports")


def export_timeline(project_id: int = 1, output_name: str = "output.mp4",
                    resolution: str = "1920x1080", fps: float = 30.0,
                    progress_cb=None) -> str:
    """Exportiert alle Timeline-Einträge als zusammengeschnittenes Video.

    Ablauf:
    1. Liest TimelineEntry-Einträge sortiert nach start_time
    2. Erstellt FFmpeg-Concat-Datei für Video-Clips
    3. Mischt Audio darunter (falls vorhanden)
    4. Gibt den Pfad zur fertigen .mp4 zurück
    """
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = EXPORT_DIR / output_name

    with Session(engine) as session:
        entries = (
            session.query(TimelineEntry)
            .filter_by(project_id=project_id)
            .order_by(TimelineEntry.start_time)
            .all()
        )
        if not entries:
            raise ValueError("Keine Timeline-Einträge zum Exportieren vorhanden")

        video_entries = [e for e in entries if e.track == "video"]
        audio_entries = [e for e in entries if e.track == "audio"]

        # Video-Clip-Pfade sammeln
        video_segments = []
        for ve in video_entries:
            clip = session.get(VideoClip, ve.media_id)
            if clip:
                video_segments.append({
                    "path": clip.file_path,
                    "start": ve.start_time,
                    "end": ve.end_time or clip.duration or 10.0,
                    "duration": clip.duration or 10.0,
                })

        # Audio-Pfad (erster Audio-Eintrag)
        audio_path = None
        audio_duration = None
        if audio_entries:
            track = session.get(AudioTrack, audio_entries[0].media_id)
            if track:
                audio_path = track.file_path
                audio_duration = track.duration

    if not video_segments:
        raise ValueError("Keine Video-Clips auf der Timeline")

    total_steps = len(video_segments) + 2
    step = 0

    # Schritt 1: Concat-Datei erstellen
    w, h = resolution.split("x")
    concat_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, prefix="pb_concat_"
    )
    try:
        for seg in video_segments:
            # Escape single quotes in path for FFmpeg
            concat_file.write(f"file '{seg['path']}'\n")
        concat_file.close()

        if progress_cb:
            step += 1
            progress_cb(step, total_steps, "Concat-Liste erstellt")

        # Schritt 2: Video zusammenfügen mit Skalierung
        filter_str = f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}"

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_file.name,
        ]

        if audio_path:
            cmd += ["-i", audio_path]

        cmd += [
            "-vf", filter_str,
            "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        ]

        if audio_path:
            cmd += [
                "-c:a", "aac", "-b:a", "192k",
                "-map", "0:v:0", "-map", "1:a:0",
                "-shortest",
            ]
        else:
            cmd += ["-an"]

        cmd.append(str(output_path))

        if progress_cb:
            step += 1
            progress_cb(step, total_steps, "FFmpeg-Export läuft...")

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg-Export fehlgeschlagen:\n{result.stderr[-500:]}")

        if progress_cb:
            step += 1
            progress_cb(step, total_steps, "Export abgeschlossen")

    finally:
        Path(concat_file.name).unlink(missing_ok=True)

    return str(output_path.resolve())


def get_timeline_summary(project_id: int = 1) -> dict:
    """Gibt eine Zusammenfassung der aktuellen Timeline zurück."""
    with Session(engine) as session:
        entries = (
            session.query(TimelineEntry)
            .filter_by(project_id=project_id)
            .all()
        )
        video_count = sum(1 for e in entries if e.track == "video")
        audio_count = sum(1 for e in entries if e.track == "audio")
        total_duration = 0.0
        for e in entries:
            if e.track == "video" and e.end_time:
                total_duration = max(total_duration, e.end_time)
        return {
            "video_clips": video_count,
            "audio_tracks": audio_count,
            "total_entries": len(entries),
            "estimated_duration": total_duration,
        }
