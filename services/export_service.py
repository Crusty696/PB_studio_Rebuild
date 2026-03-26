"""Export-Service: Fuegt Timeline-Clips via FFmpeg zu einem finalen Video zusammen.

Phase 3 Erweiterung: Crossfades, Farbkorrektur, Stem-Mix, Auto-Ducking.
Optimiert fuer viele kleine Segmente (Auto-Edit to Beat).
"""

import json as _json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path

from sqlalchemy.orm import Session
from database import engine, TimelineEntry, AudioTrack, VideoClip, APP_ROOT

logger = logging.getLogger(__name__)

EXPORT_DIR = APP_ROOT / "exports"


def _prepare_normalized_audio(audio_path: str | None, temp_files: list,
                               progress_cb=None, step: int = 0,
                               total_steps: int = 5) -> tuple[str | None, int]:
    """LUFS-Normalisierung auf Audio anwenden. Gibt (normalized_path, step) zurueck."""
    if not audio_path:
        return None, step
    if progress_cb:
        step += 1
        progress_cb(int(step / total_steps * 100), "Audio-Normalisierung (LUFS)...")
    norm_tmp = tempfile.NamedTemporaryFile(
        suffix=".wav", delete=False, prefix="pb_lufs_"
    )
    norm_tmp.close()
    temp_files.append(norm_tmp.name)
    if _normalize_audio_lufs(audio_path, norm_tmp.name):
        return norm_tmp.name, step
    return audio_path, step


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

        # Bug-12 Fix: Bulk-Load aller benötigten VideoClips verhindert N+1
        # (vorher: 1 SELECT pro Segment → bei 100 Auto-Edit Segmenten = 100 Queries)
        _vid_ids = [ve.media_id for ve in video_entries]
        _clips_by_id = (
            {c.id: c for c in session.query(VideoClip).filter(
                VideoClip.id.in_(_vid_ids)
            ).all()}
            if _vid_ids else {}
        )

        video_segments = []
        for ve in video_entries:
            clip = _clips_by_id.get(ve.media_id)
            if clip:
                source_start = ve.source_start or 0.0
                source_end = ve.source_end
                seg_duration = ve.end_time - ve.start_time if ve.end_time else (clip.duration or 10.0)
                # Source-Duration aus Source-Offsets, Fallback auf Timeline-Duration
                if source_end is not None and source_start is not None:
                    source_duration = source_end - source_start
                else:
                    source_duration = seg_duration
                video_segments.append({
                    "path": clip.file_path,
                    "start": ve.start_time,
                    "end": ve.end_time or (ve.start_time + seg_duration),
                    "duration": clip.duration or 10.0,
                    "source_start": source_start,
                    "source_duration": source_duration,
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

    # Berechne total_steps basierend auf Audio-Normalisierung
    total_steps = 5 if audio_path else 4
    step = 0

    # Bug-35 Fix: Validiere Resolution vor Split
    try:
        w, h = resolution.split("x")
    except ValueError:
        raise ValueError(f"Ungültige Auflösung Format: '{resolution}'. Erwartet: WIDTHxHEIGHT (z.B. '1920x1080')")

    # Strategie: Bei vielen Segmenten (>10) oder ohne Effekte -> Concat
    # Bei wenigen mit Effekten -> Filtergraph
    has_effects = any(
        seg["crossfade"] > 0 or seg["brightness"] != 0.0 or seg["contrast"] != 1.0
        for seg in video_segments
    )

    if has_effects:
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
        progress_cb(int(step / total_steps * 100), "Baue Concat-Liste...")

    try:
        # PERF-FIX: Nur Segmente mit Farbkorrektur vorverarbeiten.
        # Segmente mit reinem Source-Offset nutzen concat inpoint/outpoint Direktiven
        # statt separater FFmpeg-Prozesse (100 Segmente: ~200s -> ~2s).
        processed_segments = []
        for i, seg in enumerate(video_segments):
            has_color = seg["brightness"] != 0.0 or seg["contrast"] != 1.0
            source_start = seg.get("source_start", 0.0)
            source_duration = seg.get("source_duration", seg["end"] - seg["start"])

            if has_color:
                # NUR bei Farbkorrektur: Vorverarbeitung mit FFmpeg noetig
                # (concat-Protokoll unterstuetzt keine Filter)
                tmp = tempfile.NamedTemporaryFile(
                    suffix=".mp4", delete=False, prefix=f"pb_cc_{i}_"
                )
                tmp.close()
                temp_files.append(tmp.name)

                vf_parts = [
                    f"eq=brightness={seg['brightness']}:contrast={seg['contrast']}",
                    f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
                    f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}",
                ]
                vf = ",".join(vf_parts)

                cc_cmd = [
                    "ffmpeg", "-y",
                    "-ss", f"{source_start:.3f}",
                    "-i", seg["path"],
                    "-t", f"{source_duration:.3f}",
                    "-vf", vf,
                    "-c:v", "libx264", "-preset", "fast", "-crf", "23",
                    "-an", tmp.name,
                ]
                _run_ffmpeg(cc_cmd, timeout=300)
                processed_segments.append({
                    "path": tmp.name,
                    "duration": source_duration,
                    "inpoint": None,  # vorverarbeitet, kein inpoint noetig
                    "outpoint": None,
                })
            elif source_start > 0.01:
                # Source-Offset OHNE Farbkorrektur: concat inpoint/outpoint
                processed_segments.append({
                    "path": seg["path"],
                    "duration": source_duration,
                    "inpoint": source_start,
                    "outpoint": source_start + source_duration,
                })
            else:
                # Kein Offset, keine Farbkorrektur: nur duration
                processed_segments.append({
                    "path": seg["path"],
                    "duration": source_duration,
                    "inpoint": None,
                    "outpoint": None,
                })

        # Concat-Datei erstellen
        concat_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, prefix="pb_concat_"
        )
        temp_files.append(concat_file.name)

        for ps in processed_segments:
            # FFmpeg concat format: Backslashes und Single-Quotes escapen
            safe_path = ps["path"].replace("\\", "/").replace("'", "'\\''")
            concat_file.write(f"file '{safe_path}'\n")
            if ps["inpoint"] is not None:
                concat_file.write(f"inpoint {ps['inpoint']:.3f}\n")
            if ps["outpoint"] is not None:
                concat_file.write(f"outpoint {ps['outpoint']:.3f}\n")
            else:
                concat_file.write(f"duration {ps['duration']:.3f}\n")
        concat_file.close()

        if progress_cb:
            step += 1
            progress_cb(int(step / total_steps * 100), f"FFmpeg-Export ({len(video_segments)} Clips)...")

        filter_str = (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}"
        )

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_file.name,
        ]

        # LUFS-Normalisierung auf Audio anwenden (wenn vorhanden)
        normalized_audio, step = _prepare_normalized_audio(
            audio_path, temp_files, progress_cb, step, total_steps
        )

        if normalized_audio:
            cmd += ["-i", normalized_audio]

        cmd += ["-vf", filter_str,
                "-c:v", "libx264", "-preset", "fast", "-crf", "23"]

        if normalized_audio:
            cmd += ["-c:a", "aac", "-b:a", "192k",
                    "-map", "0:v:0", "-map", "1:a:0", "-shortest"]
        else:
            cmd += ["-an"]

        cmd.append(str(output_path))

        _run_ffmpeg(cmd, timeout=900)

        if progress_cb:
            step += 1
            progress_cb(100, "Export abgeschlossen")

    finally:
        for tf in temp_files:
            Path(tf).unlink(missing_ok=True)

    if not Path(output_path).exists() or Path(output_path).stat().st_size == 0:
        raise RuntimeError(f"FFmpeg-Export fehlgeschlagen: Ausgabedatei fehlt oder leer: {output_path}")
    return str(Path(output_path).resolve())


def _export_with_filtergraph(video_segments, audio_path, output_path,
                             w, h, fps, progress_cb, total_steps):
    """Komplexer Export mit Filtergraph (Crossfades + Farbkorrektur)."""
    step = 0
    temp_files = []

    if progress_cb:
        step += 1
        progress_cb(int(step / total_steps * 100), "Baue FFmpeg-Kommando...")

    cmd = ["ffmpeg", "-y"]
    for seg in video_segments:
        source_start = seg.get("source_start", 0.0)
        source_duration = seg.get("source_duration", seg["end"] - seg["start"])
        if source_start > 0.01:
            cmd += ["-ss", f"{source_start:.3f}"]
        cmd += ["-t", f"{source_duration:.3f}", "-i", seg["path"]]
    # LUFS-Normalisierung auf Audio anwenden (wenn vorhanden)
    normalized_audio, step = _prepare_normalized_audio(
        audio_path, temp_files, progress_cb, step, total_steps
    )

    if normalized_audio:
        cmd += ["-i", normalized_audio]

    n = len(video_segments)
    audio_input_idx = n if normalized_audio else None

    if progress_cb:
        step += 1
        progress_cb(int(step / total_steps * 100), "Filtergraph wird erstellt...")

    filter_parts = []
    for i, seg in enumerate(video_segments):
        base_filter = (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,"
            f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}"
        )
        if seg["brightness"] != 0.0 or seg["contrast"] != 1.0:
            base_filter += f",eq=brightness={seg['brightness']}:contrast={seg['contrast']}"
        filter_parts.append(f"[{i}:v]{base_filter}[v{i}]")

    # Segment-Dauern: Source-Duration wenn vorhanden, sonst Timeline-Duration
    seg_durations = [
        seg.get("source_duration", seg["end"] - seg["start"])
        for seg in video_segments
    ]

    current_label = None
    if n == 0:
        raise ValueError("Keine Video-Segmente in _export_with_filtergraph()")
    elif n == 1:
        current_label = "v0"
    else:
        # F-014 Fix: Kumulativer Offset-Akkumulator fuer korrekte xfade-Berechnung
        accumulated_duration = seg_durations[0]

        xfade_dur = min(video_segments[1].get("crossfade", 0.0), 2.0)
        if xfade_dur > 0:
            offset = max(0.1, accumulated_duration - xfade_dur)
            filter_parts.append(
                f"[v0][v1]xfade=transition=fade:duration={xfade_dur}:offset={offset}[xf0]"
            )
            accumulated_duration = accumulated_duration + seg_durations[1] - xfade_dur
        else:
            filter_parts.append("[v0][v1]concat=n=2:v=1:a=0[xf0]")
            accumulated_duration += seg_durations[1]
        current_label = "xf0"

        for i in range(2, n):
            xfade_dur = min(video_segments[i].get("crossfade", 0.0), 2.0)
            if xfade_dur > 0:
                offset = max(0.1, accumulated_duration - xfade_dur)
                filter_parts.append(
                    f"[{current_label}][v{i}]xfade=transition=fade:"
                    f"duration={xfade_dur}:offset={offset}[xf{i-1}]"
                )
                accumulated_duration = accumulated_duration + seg_durations[i] - xfade_dur
            else:
                filter_parts.append(
                    f"[{current_label}][v{i}]concat=n=2:v=1:a=0[xf{i-1}]"
                )
                accumulated_duration += seg_durations[i]
            current_label = f"xf{i-1}"

    filter_complex = ";".join(filter_parts)
    cmd += ["-filter_complex", filter_complex]
    cmd += ["-map", f"[{current_label}]"]

    if normalized_audio and audio_input_idx is not None:
        cmd += ["-map", f"{audio_input_idx}:a:0",
                "-c:a", "aac", "-b:a", "192k", "-shortest"]
    else:
        cmd += ["-an"]

    cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "23"]
    cmd.append(str(output_path))

    if progress_cb:
        step += 1
        progress_cb(int(step / total_steps * 100), "FFmpeg-Export mit Effekten...")

    try:
        _run_ffmpeg(cmd, timeout=1800)
    finally:
        for tf in temp_files:
            Path(tf).unlink(missing_ok=True)

    if progress_cb:
        step += 1
        progress_cb(100, "Export mit Effekten abgeschlossen")

    if not Path(output_path).exists() or Path(output_path).stat().st_size == 0:
        raise RuntimeError(f"FFmpeg-Export fehlgeschlagen: Ausgabedatei fehlt oder leer: {output_path}")
    return str(Path(output_path).resolve())


def _normalize_audio_lufs(input_path: str, output_path: str,
                          target_lufs: float = -14.0) -> bool:
    """LUFS Zwei-Pass Audio-Normalisierung via FFmpeg loudnorm.

    Pass 1: Misst die integrierte Lautstaerke (I), Loudness Range (LRA),
            True Peak (TP) und Threshold.
    Pass 2: Wendet die gemessenen Werte an um auf target_lufs zu normalisieren.

    Returns True bei Erfolg, False bei Fehler (Original wird dann verwendet).
    """
    try:
        # Pass 1: Lautstaerke messen
        kwargs = {}
        if sys.platform == "win32":
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        measure_cmd = [
            "ffmpeg", "-i", input_path,
            "-af", "loudnorm=print_format=json",
            "-f", "null", "-"
        ]
        result = subprocess.run(
            measure_cmd, capture_output=True, text=True, timeout=300,
            encoding="utf-8", errors="replace", **kwargs
        )
        if result.returncode != 0:
            logger.warning("[LUFS] Pass 1 fehlgeschlagen (rc=%d): %s",
                           result.returncode, result.stderr[:200])
            return False
        # loudnorm JSON steht in stderr
        stderr = result.stderr
        # Finde den JSON-Block in der Ausgabe
        json_start = stderr.rfind("{")
        json_end = stderr.rfind("}") + 1
        if json_start < 0 or json_end <= json_start:
            logger.warning("[LUFS] Konnte loudnorm-Messung nicht parsen")
            return False

        measured = _json.loads(stderr[json_start:json_end])
        input_i = measured.get("input_i", "-24.0")
        input_lra = measured.get("input_lra", "7.0")
        input_tp = measured.get("input_tp", "-2.0")
        input_thresh = measured.get("input_thresh", "-34.0")

        # Pass 2: Normalisierung anwenden
        loudnorm_filter = (
            f"loudnorm=I={target_lufs}:LRA=11:TP=-1"
            f":measured_I={input_i}:measured_LRA={input_lra}"
            f":measured_TP={input_tp}:measured_thresh={input_thresh}"
            f":linear=true"
        )
        norm_cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-af", loudnorm_filter,
            "-ar", "48000",
            "-c:a", "pcm_s24le",
            output_path,
        ]
        pass2_result = subprocess.run(
            norm_cmd, capture_output=True, text=True, timeout=600,
            encoding="utf-8", errors="replace", **kwargs
        )
        if pass2_result.returncode != 0:
            logger.warning("[LUFS] Pass 2 fehlgeschlagen (rc=%d): %s",
                           pass2_result.returncode, pass2_result.stderr[:200])
            return False
        if Path(output_path).exists() and Path(output_path).stat().st_size > 0:
            logger.info("[LUFS] Normalisierung erfolgreich: %s -> %.1f LUFS",
                        input_path, target_lufs)
            return True
        return False
    except Exception as e:
        logger.warning("[LUFS] Normalisierung fehlgeschlagen: %s", e)
        return False


def _run_ffmpeg(cmd: list[str], timeout: int = 600):
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=timeout,
        encoding="utf-8", errors="replace", **kwargs
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
