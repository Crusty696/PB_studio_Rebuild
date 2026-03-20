"""Pacing-Service: Intelligenter Beat-Edit mit Beatgrid und Pacing-Kurve.

SEKTOR 2+3: Jeder Schnitt faellt AUSNAHMSLOS auf einen Beat-Timestamp.
Die Pacing-Kurve steuert die Dichte (jeden Beat, jeden 2., 4., 8., 16. Beat).
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
    manual_density_curve: list[float] | None = None  # Per-sample density override (0.0-1.0)


@dataclass
class CutPoint:
    """Ein einzelner Schnittpunkt auf der Timeline."""
    time: float              # Zeitpunkt in Sekunden
    source: str              # "beat", "scene", "energy", "drum"
    strength: float          # 0.0-1.0: Wie stark der Cut-Impuls ist


def _get_beat_positions(audio_id: int | None) -> list[float]:
    """Laedt die exakten Beat-Positionen aus dem Beatgrid der DB."""
    if audio_id is None:
        return []
    with Session(engine) as session:
        track = session.get(AudioTrack, audio_id)
        if not track or not track.beatgrid:
            return []
        bg = track.beatgrid
        if bg.beat_positions:
            try:
                positions = json.loads(bg.beat_positions)
                return [float(p) for p in positions]
            except (json.JSONDecodeError, TypeError):
                pass
        # Fallback: Beatgrid aus BPM + Offset generieren
        if bg.bpm and bg.bpm > 0:
            interval = 60.0 / bg.bpm
            duration = track.duration or 300.0
            t = bg.offset or 0.0
            positions = []
            while t < duration:
                positions.append(round(t, 4))
                t += interval
            return positions
    return []


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


def _density_to_beat_step(density: float) -> int:
    """Wandelt einen Dichte-Wert (0.0-1.0) in einen Beat-Schritt um.

    Hohe Dichte (>0.8)  -> jeden Beat       (step=1)
    Mittlere (0.5-0.8)  -> jeden 2. Beat    (step=2)
    Normal (0.3-0.5)    -> jeden 4. Beat    (step=4)  (Downbeats)
    Niedrig (0.15-0.3)  -> jeden 8. Beat    (step=8)
    Sehr niedrig (<0.15)-> jeden 16. Beat   (step=16)
    """
    if density >= 0.8:
        return 1
    elif density >= 0.5:
        return 2
    elif density >= 0.3:
        return 4
    elif density >= 0.15:
        return 8
    else:
        return 16


def calculate_cut_points(
    audio_id: int | None,
    video_id: int | None,
    settings: PacingSettings,
    total_duration: float = 60.0,
) -> list[CutPoint]:
    """Berechnet Schnittpunkte EXAKT auf Beat-Timestamps aus dem Beatgrid.

    SEKTOR 2: Kein Cut darf JEMALS ausserhalb eines Beat-Timestamps liegen.
    SEKTOR 3: Die Pacing-Kurve steuert, WELCHE Beats als Cuts gewaehlt werden.
    """
    beats = _get_beat_positions(audio_id)
    cuts: list[CutPoint] = []

    if beats:
        # -- Beat-basierte Cuts mit Pacing-Kurven-Modulation --
        # Basis-Beat-Step aus dem Tempo-Slider
        if settings.tempo >= 80:
            base_step = 1   # Jeden Beat
        elif settings.tempo >= 60:
            base_step = 2   # Jeden 2. Beat
        elif settings.tempo >= 40:
            base_step = 4   # Jeden 4. Beat (Downbeat/Takt)
        elif settings.tempo >= 20:
            base_step = 8   # Jeden 8. Beat
        else:
            base_step = 16  # Jeden 16. Beat

        # Pacing-Kurve laden (200 Samples ueber die Song-Dauer)
        curve = settings.manual_density_curve
        num_curve_samples = len(curve) if curve else 0

        # Ueber alle Beats iterieren und anhand der Kurve filtern
        for i, beat_time in enumerate(beats):
            if beat_time >= total_duration:
                break

            # Effektiven Step berechnen: Kombination aus Slider + Kurve
            if curve and num_curve_samples > 0:
                # Pacing-Kurve am aktuellen Zeitpunkt auslesen
                curve_idx = int((beat_time / total_duration) * (num_curve_samples - 1))
                curve_idx = max(0, min(curve_idx, num_curve_samples - 1))
                density = curve[curve_idx]
                # Kurve moduliert den Beat-Step
                curve_step = _density_to_beat_step(density)
                # Verwende den kuerzeren Step (= mehr Cuts bei hoher Dichte)
                effective_step = min(base_step, curve_step) if density >= 0.5 else max(base_step, curve_step)
            else:
                effective_step = base_step

            # Pruefe ob dieser Beat ein Cut-Punkt ist
            if i % effective_step == 0:
                strength = min(1.0, settings.energy / 100.0 + 0.3)
                # Staerkere Cuts auf Downbeats (jeder 4. Beat)
                if i % 4 == 0:
                    strength = min(1.0, strength + 0.15)
                cuts.append(CutPoint(
                    time=round(beat_time, 4),
                    source="beat",
                    strength=round(strength, 3),
                ))
    else:
        # Fallback: BPM-basierte Beats generieren (kein Beatgrid vorhanden)
        bpm = _get_bpm(audio_id)
        if bpm and bpm > 0:
            interval = 60.0 / bpm
            t = 0.0
            i = 0
            while t < total_duration:
                strength = min(1.0, settings.energy / 100.0 + 0.3)
                if i % 4 == 0:
                    strength = min(1.0, strength + 0.15)
                cuts.append(CutPoint(time=round(t, 3), source="beat", strength=strength))
                t += interval
                i += 1
        else:
            # Letzter Fallback: Feste Intervalle
            interval = max(1.0, 8.0 - (settings.tempo / 100.0 * 7.0))
            t = interval
            while t < total_duration:
                strength = min(1.0, settings.energy / 100.0 + 0.3)
                cuts.append(CutPoint(time=round(t, 3), source="energy", strength=strength))
                t += interval

    # Szenen-basierte Cuts (zur Info, aber nur auf dem naechsten Beat!)
    scenes = _get_scenes(video_id)
    if beats and scenes:
        beats_arr = np.array(beats)
        for scene in scenes:
            # Snape Scene-Start auf den naechsten Beat
            idx = np.searchsorted(beats_arr, scene.start_time)
            if idx < len(beats_arr):
                snapped = beats_arr[idx]
                # Nur wenn nicht schon ein Beat-Cut dort existiert
                if not any(abs(c.time - snapped) < 0.05 for c in cuts):
                    cuts.append(CutPoint(
                        time=round(float(snapped), 4),
                        source="scene",
                        strength=min(1.0, (scene.energy or 0.5) + 0.2),
                    ))

    # Filtern nach Cut-Density-Slider
    threshold = 1.0 - (settings.cut_density / 100.0)
    cuts = [c for c in cuts if c.strength >= threshold]

    # Sortieren und Duplikate entfernen (min. 0.1s Abstand)
    cuts.sort(key=lambda c: c.time)
    filtered: list[CutPoint] = []
    for cut in cuts:
        if not filtered or (cut.time - filtered[-1].time) >= 0.1:
            filtered.append(cut)

    return filtered


def calculate_drum_cuts(audio_id: int, total_duration: float = 60.0,
                        energy_threshold: float = 0.3) -> list[CutPoint]:
    """Berechnet Schnittpunkte basierend auf dem Drums-Stem.

    SEKTOR 2 Konformitaet: Drum-Onsets werden auf den naechsten Beat gesnappt!
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

    # Beat-Positionen laden fuer Snapping
    beats = _get_beat_positions(audio_id)
    beats_arr = np.array(beats) if beats else None

    # RMS pro Onset fuer Staerke-Bewertung
    rms = librosa.feature.rms(y=y)[0]
    max_rms = rms.max() if rms.max() > 0 else 1.0

    cuts = []
    used_beats = set()

    for onset_time in onset_times:
        if onset_time >= total_duration:
            break
        frame_idx = min(librosa.time_to_frames(onset_time, sr=sr), len(rms) - 1)
        strength = float(rms[frame_idx] / max_rms)
        if strength >= energy_threshold:
            # Snappe auf den naechsten Beat
            if beats_arr is not None and len(beats_arr) > 0:
                idx = np.argmin(np.abs(beats_arr - onset_time))
                snapped_time = float(beats_arr[idx])
                # Nur wenn der naechste Beat nicht zu weit weg ist (max 0.15s)
                if abs(snapped_time - onset_time) <= 0.15 and snapped_time not in used_beats:
                    used_beats.add(snapped_time)
                    cuts.append(CutPoint(
                        time=round(snapped_time, 4),
                        source="drum",
                        strength=round(strength, 3),
                    ))
            else:
                # Ohne Beatgrid: Rohwerte verwenden
                cuts.append(CutPoint(
                    time=round(float(onset_time), 3),
                    source="drum",
                    strength=round(strength, 3),
                ))

    return cuts


def auto_edit_to_beats(
    audio_id: int,
    video_clip_ids: list[int],
    total_duration: float = 60.0,
    pacing_curve: list[float] | None = None,
    tempo: int = 50,
) -> list[dict]:
    """SEKTOR 2+3: Intelligenter Auto-Edit basierend auf Beatgrid + Pacing-Kurve.

    REGELN:
    - Jeder Schnitt faellt EXAKT auf einen Beat-Timestamp aus dem Beatgrid.
    - Die Pacing-Kurve bestimmt die Dichte (welche Beats genutzt werden).
    - Video-Clips werden lueckenlos auf die Timeline gelegt.
    - Zu kurze Clips werden geloopt (wiederholt), nicht uebersprungen.

    Returns: [{"video_id": int, "start": float, "end": float, "source_start": float}, ...]
    """
    # 1. Beat-Positionen aus dem Beatgrid laden
    beats = _get_beat_positions(audio_id)

    # Fallback: BPM-basierte Beats
    if not beats:
        bpm = _get_bpm(audio_id)
        if bpm and bpm > 0:
            interval = 60.0 / bpm
            t = 0.0
            beats = []
            while t < total_duration:
                beats.append(round(t, 4))
                t += interval

    if not beats or not video_clip_ids:
        return []

    # 2. Cut-Beats basierend auf Pacing-Kurve + Tempo auswaehlen
    cut_beats = _select_cut_beats(beats, total_duration, pacing_curve, tempo)

    # Beat 0 immer als Startpunkt
    if not cut_beats or cut_beats[0] > 0.01:
        cut_beats.insert(0, 0.0)
    # Ende hinzufuegen
    if cut_beats[-1] < total_duration - 0.1:
        cut_beats.append(total_duration)

    # 3. Video-Clip-Dauern holen
    clip_durations = {}
    with Session(engine) as session:
        for vid in video_clip_ids:
            clip = session.get(VideoClip, vid)
            if clip:
                clip_durations[vid] = clip.duration or 10.0

    if not clip_durations:
        return []

    # 4. Segmente erzeugen: Clips lueckenlos auf Beat-Grenzen verteilen
    segments = []
    clip_idx = 0
    available_clips = [vid for vid in video_clip_ids if vid in clip_durations]
    if not available_clips:
        return []

    # Clip-interner Offset-Tracker (fuer Multi-Segment-Nutzung eines Clips)
    clip_offsets: dict[int, float] = {vid: 0.0 for vid in available_clips}

    for i in range(len(cut_beats) - 1):
        seg_start = cut_beats[i]
        seg_end = cut_beats[i + 1]
        seg_duration = seg_end - seg_start

        # Mindestdauer fuer ein Segment: 0.2 Sekunden
        if seg_duration < 0.2:
            continue

        # Clip rotieren
        vid = available_clips[clip_idx % len(available_clips)]
        vid_duration = clip_durations[vid]
        source_start = clip_offsets[vid]

        # Pruefen ob genug Material vorhanden ist
        remaining_in_clip = vid_duration - source_start
        if remaining_in_clip < seg_duration:
            # Loop: Clip von vorne starten
            source_start = 0.0
            clip_offsets[vid] = 0.0

        segments.append({
            "video_id": vid,
            "start": round(seg_start, 4),
            "end": round(seg_end, 4),
            "source_start": round(source_start, 4),
        })

        # Offset im Quell-Clip weiterbewegen
        clip_offsets[vid] = source_start + seg_duration
        if clip_offsets[vid] >= vid_duration:
            clip_offsets[vid] = 0.0  # Loop reset

        clip_idx += 1

    return segments


def _select_cut_beats(
    beats: list[float],
    total_duration: float,
    pacing_curve: list[float] | None,
    tempo: int,
) -> list[float]:
    """Waehlt die Beat-Timestamps aus, auf denen geschnitten wird.

    SEKTOR 3: Die Pacing-Kurve bestimmt die lokale Schnitt-Dichte.
    """
    if not beats:
        return []

    # Basis-Step aus Tempo-Slider
    if tempo >= 80:
        base_step = 1
    elif tempo >= 60:
        base_step = 2
    elif tempo >= 40:
        base_step = 4
    elif tempo >= 20:
        base_step = 8
    else:
        base_step = 16

    num_curve_samples = len(pacing_curve) if pacing_curve else 0
    selected: list[float] = []

    for i, beat_time in enumerate(beats):
        if beat_time >= total_duration:
            break

        # Effektiven Step berechnen
        if pacing_curve and num_curve_samples > 0:
            curve_idx = int((beat_time / total_duration) * (num_curve_samples - 1))
            curve_idx = max(0, min(curve_idx, num_curve_samples - 1))
            density = pacing_curve[curve_idx]
            curve_step = _density_to_beat_step(density)
            # Bei hoher Dichte: kuerzeren Step nehmen (mehr Cuts)
            # Bei niedriger Dichte: laengeren Step nehmen (weniger Cuts)
            effective_step = min(base_step, curve_step) if density >= 0.5 else max(base_step, curve_step)
        else:
            effective_step = base_step

        if i % effective_step == 0:
            selected.append(beat_time)

    return selected
