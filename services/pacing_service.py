"""Pacing-Service: Berechnet Schnittpunkte basierend auf BPM, Szenen und UI-Parametern.

Phase 2 Erweiterung: Drum-Track-basierte Cuts (Kick/Snare Detection).
"""

import json
from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session
from database import engine, AudioTrack, VideoClip, Scene, Beatgrid


@dataclass
class PacingSettings:
    """UI-Slider-Einstellungen fuer die Timeline-Generierung."""
    tempo: int = 50          # 0-100: langsam -> schnell
    energy: int = 50         # 0-100: ruhig -> energetisch
    cut_density: int = 50    # 0-100: wenig Schnitte -> viele Schnitte
    vibe: str = ""           # Freitext-Stimmung


@dataclass
class CutPoint:
    """Ein einzelner Schnittpunkt auf der Timeline."""
    time: float              # Zeitpunkt in Sekunden
    source: str              # "beat", "scene", "energy", "drum"
    strength: float          # 0.0-1.0: Wie stark der Cut-Impuls ist


def calculate_cut_points(
    audio_id: int | None,
    video_id: int | None,
    settings: PacingSettings,
    total_duration: float = 60.0,
) -> list[CutPoint]:
    """Berechnet Schnittpunkte basierend auf Audio-BPM, Video-Szenen und Slider-Settings."""
    cuts: list[CutPoint] = []

    # Beat-basierte Cuts aus Audio-BPM
    bpm = _get_bpm(audio_id)
    if bpm and bpm > 0:
        beat_interval = 60.0 / bpm

        if settings.tempo < 25:
            divisor = 4
        elif settings.tempo < 50:
            divisor = 2
        elif settings.tempo < 75:
            divisor = 1
        else:
            divisor = 0.5

        cut_interval = beat_interval * divisor
        t = cut_interval
        while t < total_duration:
            strength = min(1.0, settings.energy / 100.0 + 0.3)
            cuts.append(CutPoint(time=round(t, 3), source="beat", strength=strength))
            t += cut_interval
    else:
        interval = max(1.0, 8.0 - (settings.tempo / 100.0 * 7.0))
        t = interval
        while t < total_duration:
            strength = min(1.0, settings.energy / 100.0 + 0.3)
            cuts.append(CutPoint(time=round(t, 3), source="energy", strength=strength))
            t += interval

    # Szenen-basierte Cuts aus Video
    scenes = _get_scenes(video_id)
    for scene in scenes:
        cuts.append(CutPoint(
            time=round(scene.start_time, 3),
            source="scene",
            strength=min(1.0, (scene.energy or 0.5) + 0.2),
        ))

    # Filtern nach Cut-Density
    threshold = 1.0 - (settings.cut_density / 100.0)
    cuts = [c for c in cuts if c.strength >= threshold]

    # Sortieren und Duplikate entfernen
    cuts.sort(key=lambda c: c.time)
    filtered: list[CutPoint] = []
    for cut in cuts:
        if not filtered or (cut.time - filtered[-1].time) >= 0.1:
            filtered.append(cut)

    return filtered


def calculate_drum_cuts(audio_id: int, total_duration: float = 60.0,
                        energy_threshold: float = 0.3) -> list[CutPoint]:
    """Phase 2: Berechnet Schnittpunkte basierend auf dem Drums-Stem.

    Analysiert den extrahierten Drums-Track und setzt Cuts auf harte Kicks/Snares.
    """
    with Session(engine) as session:
        track = session.get(AudioTrack, audio_id)
        if not track or not track.stem_drums_path:
            return []
        drums_path = track.stem_drums_path

    try:
        import librosa
        y, sr = librosa.load(drums_path, sr=22050, mono=True)
    except Exception:
        return []

    # Onset Detection auf dem Drums-Track
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_frames = librosa.onset.onset_detect(
        onset_envelope=onset_env, sr=sr, backtrack=False
    )
    onset_times = librosa.frames_to_time(onset_frames, sr=sr)

    # RMS pro Onset fuer Staerke-Bewertung
    rms = librosa.feature.rms(y=y)[0]
    max_rms = rms.max() if rms.max() > 0 else 1.0

    cuts = []
    for onset_time in onset_times:
        if onset_time >= total_duration:
            break
        # Staerke basierend auf lokaler Energie
        frame_idx = min(librosa.time_to_frames(onset_time, sr=sr), len(rms) - 1)
        strength = float(rms[frame_idx] / max_rms)
        if strength >= energy_threshold:
            cuts.append(CutPoint(
                time=round(float(onset_time), 3),
                source="drum",
                strength=round(strength, 3),
            ))

    return cuts


def auto_edit_to_beats(audio_id: int, video_clip_ids: list[int],
                       total_duration: float = 60.0) -> list[dict]:
    """Phase 2: Auto-Edit to Beat.

    Verteilt Video-Clips automatisch auf die Drum-Beats.
    Gibt eine Liste von Timeline-Segment-Dicts zurueck.

    Returns: [{"video_id": int, "start": float, "end": float}, ...]
    """
    drum_cuts = calculate_drum_cuts(audio_id, total_duration)
    # Fallback auf BPM-Beats wenn weniger als 10 Drum-Cuts
    if len(drum_cuts) < 10:
        bpm = _get_bpm(audio_id)
        if bpm and bpm > 0:
            interval = 60.0 / bpm
            drum_cuts = []
            t = 0.0
            while t < total_duration:
                drum_cuts.append(CutPoint(time=round(t, 3), source="beat", strength=0.8))
                t += interval

    if not drum_cuts or not video_clip_ids:
        return []

    # Video-Clip-Dauern holen
    clip_durations = {}
    with Session(engine) as session:
        for vid in video_clip_ids:
            clip = session.get(VideoClip, vid)
            if clip:
                clip_durations[vid] = clip.duration or 10.0

    # Cuts als Zeitpunkte: [0, cut1, cut2, ..., total_duration]
    cut_times = [0.0] + [c.time for c in drum_cuts] + [total_duration]

    segments = []
    clip_idx = 0
    available_clips = list(video_clip_ids)

    for i in range(len(cut_times) - 1):
        seg_start = cut_times[i]
        seg_end = cut_times[i + 1]
        seg_duration = seg_end - seg_start

        # Mindestdauer fuer ein Segment: 0.3 Sekunden
        if seg_duration < 0.3:
            continue

        # Clips rotieren
        vid = available_clips[clip_idx % len(available_clips)]
        clip_idx += 1

        segments.append({
            "video_id": vid,
            "start": round(seg_start, 3),
            "end": round(seg_end, 3),
        })

    return segments


def _get_bpm(audio_id: int | None) -> float | None:
    if audio_id is None:
        return None
    with Session(engine) as session:
        track = session.get(AudioTrack, audio_id)
        return track.bpm if track else None


def _get_scenes(video_id: int | None) -> list[Scene]:
    if video_id is None:
        return []
    with Session(engine) as session:
        clip = session.get(VideoClip, video_id)
        if clip is None:
            return []
        return list(clip.scenes)
