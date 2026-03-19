"""Export-Service: Fuegt Timeline-Clips via FFmpeg zu einem finalen Video zusammen.

Phase 3 Erweiterung: Crossfades, Farbkorrektur, Stem-Mix, Auto-Ducking.
Optimiert fuer viele kleine Segmente (Auto-Edit to Beat).
"""

import subprocess
import sys
import tempfile
from pathlib import Path

from sqlalchemy.orm import Session
from database import engine, TimelineEntry, AudioTrack, VideoClip

EXPORT_DIR = Path("exports")


def export_timeline(project_id: int = 1, output_name: str = "output.mp4",
                    resolution: str = "1920x1080", fps: float = 30.0,
                    progress_cb=None) -> str:
    """Exportiert alle Timeline-Eintraege als zusammengeschnittenes Video."""
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
            raise ValueError("Keine Timeline-Eintraege zum Exportieren vorhanden")

        video_entries = [e for e in entries if e.track == "video"]
        audio_entries = [e for e in entries if e.track == "audio"]

        video_segments = []
        for ve in video_entries:
            clip = session.get(VideoClip, ve.media_id)
            if clip:
                video_segments.append({
                    "path": clip.file_path,
                    "start": ve.start_time,
                    "end": ve.end_time or (ve.start_time + (clip.duration or 10.0)),
                    "duration": clip.duration or 10.0,
                    "crossfade": ve.crossfade_duration or 0.0,
                    "brightness": ve.brightness or 0.0,
                    "contrast": ve.contrast or 1.0,
                })

        audio_path = None
        if audio_entries:
            track = session.get(AudioTrack, audio_entries[0].media_id)
            if track:
                audio_path = track.file_path

    if not video_segments:
        raise ValueError("Keine Video-Clips auf der Timeline")

    total_steps = 4
    step = 0

    w, h = resolution.split("x")

    # Strategie: Bei vielen Segmenten (>10) oder ohne Effekte -> Concat
    # Bei wenigen mit Effekten -> Filtergraph
    has_effects = any(
        seg["crossfade"] > 0 or seg["brightness"] != 0.0 or seg["contrast"] != 1.0
        for seg in video_segments
    )

    if has_effects and len(video_segments) <= 10:
        return _export_with_filtergraph(
            video_segments, audio_path, output_path,
            w, h, fps, progress_cb, total_steps
        )
    else:
        return _export_optimized_concat(
            video_segments, audio_path, output_path,
            w, h, fps, progress_cb, total_steps
        )


def _export_optimized_concat(video_segments, audio_path, output_path,
                              w, h, fps, progress_cb, total_steps):
    """CRIT-02 Fix: Concat-Export mit per-Segment Farbkorrektur via Vorverarbeitung."""
    step = 0
    temp_files = []

    if progress_cb:
        step += 1
        progress_cb(step, total_steps, "Baue Concat-Liste...")

    try:
        # CRIT-02: Segmente mit Farbkorrektur vorverarbeiten
        processed_segments = []
        for i, seg in enumerate(video_segments):
            has_color = seg["brightness"] != 0.0 or seg["contrast"] != 1.0
            seg_duration = seg["end"] - seg["start"]

            if has_color:
                # Vorverarbeitung: Farbkorrektur auf temp-Datei anwenden
                tmp = tempfile.NamedTemporaryFile(
                    suffix=".mp4", delete=False, prefix=f"pb_cc_{i}_"
                )
                tmp.close()
                temp_files.append(tmp.name)

                vf = (
                    f"eq=brightness={seg['brightness']}:contrast={seg['contrast']},"
                    f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                    f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}"
                )
                cc_cmd = [
                    "ffmpeg", "-y", "-i", seg["path"],
                    "-t", f"{seg_duration:.3f}",
                    "-vf", vf,
                    "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-an", tmp.name,
                ]
                _run_ffmpeg(cc_cmd, timeout=300)
                processed_segments.append({
                    "path": tmp.name, "duration": seg_duration,
                })
            else:
                processed_segments.append({
                    "path": seg["path"], "duration": seg_duration,
                })

        # Concat-Datei erstellen
        concat_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, prefix="pb_concat_"
        )
        temp_files.append(concat_file.name)

        for ps in processed_segments:
            safe_path = ps["path"].replace("'", "'\\''")
            concat_file.write(f"file '{safe_path}'\n")
            concat_file.write(f"duration {ps['duration']:.3f}\n")
        concat_file.close()

        if progress_cb:
            step += 1
            progress_cb(step, total_steps, f"FFmpeg-Export ({len(video_segments)} Clips)...")

        filter_str = (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}"
        )

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_file.name,
        ]

        if audio_path:
            cmd += ["-i", audio_path]

        cmd += ["-vf", filter_str,
                "-c:v", "libx264", "-preset", "fast", "-crf", "23"]

        if audio_path:
            cmd += ["-c:a", "aac", "-b:a", "192k",
                    "-map", "0:v:0", "-map", "1:a:0", "-shortest"]
        else:
            cmd += ["-an"]

        cmd.append(str(output_path))

        _run_ffmpeg(cmd, timeout=900)

        if progress_cb:
            step += 1
            progress_cb(step, total_steps, "Export abgeschlossen")

    finally:
        for tf in temp_files:
            Path(tf).unlink(missing_ok=True)

    return str(Path(output_path).resolve())


def _export_with_filtergraph(video_segments, audio_path, output_path,
                             w, h, fps, progress_cb, total_steps):
    """Komplexer Export mit Filtergraph (Crossfades + Farbkorrektur)."""
    step = 0

    cmd = ["ffmpeg", "-y"]
    for seg in video_segments:
        cmd += ["-i", seg["path"]]
    if audio_path:
        cmd += ["-i", audio_path]

    n = len(video_segments)
    audio_input_idx = n if audio_path else None

    if progress_cb:
        step += 1
        progress_cb(step, total_steps, "Filtergraph wird erstellt...")

    filter_parts = []
    for i, seg in enumerate(video_segments):
        base_filter = (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}"
        )
        if seg["brightness"] != 0.0 or seg["contrast"] != 1.0:
            base_filter += f",eq=brightness={seg['brightness']}:contrast={seg['contrast']}"
        filter_parts.append(f"[{i}:v]{base_filter}[v{i}]")

    # CRIT-03 Fix: Berechne Segment-Dauern aus start/end statt Quell-Clip-Dauer
    seg_durations = [seg["end"] - seg["start"] for seg in video_segments]

    current_label = None
    if n == 1:
        current_label = "v0"
    else:
        xfade_dur = min(video_segments[1].get("crossfade", 0.0), 2.0)
        if xfade_dur > 0:
            offset = max(0.1, seg_durations[0] - xfade_dur)
            filter_parts.append(
                f"[v0][v1]xfade=transition=fade:duration={xfade_dur}:offset={offset}[xf0]"
            )
        else:
            filter_parts.append("[v0][v1]concat=n=2:v=1:a=0[xf0]")
        current_label = "xf0"

        for i in range(2, n):
            xfade_dur = min(video_segments[i].get("crossfade", 0.0), 2.0)
            if xfade_dur > 0:
                prev_seg_dur = seg_durations[i - 1]
                offset = max(0.1, prev_seg_dur - xfade_dur)
                filter_parts.append(
                    f"[{current_label}][v{i}]xfade=transition=fade:"
                    f"duration={xfade_dur}:offset={offset}[xf{i-1}]"
                )
            else:
                filter_parts.append(
                    f"[{current_label}][v{i}]concat=n=2:v=1:a=0[xf{i-1}]"
                )
            current_label = f"xf{i-1}"

    filter_complex = ";".join(filter_parts)
    cmd += ["-filter_complex", filter_complex]
    cmd += ["-map", f"[{current_label}]"]

    if audio_path and audio_input_idx is not None:
        cmd += ["-map", f"{audio_input_idx}:a:0",
                "-c:a", "aac", "-b:a", "192k", "-shortest"]
    else:
        cmd += ["-an"]

    cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "23"]
    cmd.append(str(output_path))

    if progress_cb:
        step += 1
        progress_cb(step, total_steps, "FFmpeg-Export mit Effekten...")

    _run_ffmpeg(cmd)

    if progress_cb:
        step += 1
        progress_cb(step, total_steps, "Export mit Effekten abgeschlossen")

    return str(Path(output_path).resolve())


def _run_ffmpeg(cmd: list[str], timeout: int = 600):
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout, **kwargs
    )
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg fehlgeschlagen:\n{result.stderr[-500:]}")


def get_timeline_summary(project_id: int = 1) -> dict:
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
