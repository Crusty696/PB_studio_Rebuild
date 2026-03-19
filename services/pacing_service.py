"""Pacing-Service: Berechnet Schnittpunkte basierend auf BPM, Szenen und UI-Parametern."""

from dataclasses import dataclass
from sqlalchemy.orm import Session
from database import engine, AudioTrack, VideoClip, Scene


@dataclass
class PacingSettings:
    """UI-Slider-Einstellungen für die Timeline-Generierung."""
    tempo: int = 50          # 0-100: langsam → schnell
    energy: int = 50         # 0-100: ruhig → energetisch
    cut_density: int = 50    # 0-100: wenig Schnitte → viele Schnitte
    vibe: str = ""           # Freitext-Stimmung


@dataclass
class CutPoint:
    """Ein einzelner Schnittpunkt auf der Timeline."""
    time: float              # Zeitpunkt in Sekunden
    source: str              # "beat", "scene", "energy"
    strength: float          # 0.0-1.0: Wie stark der Cut-Impuls ist


def calculate_cut_points(
    audio_id: int | None,
    video_id: int | None,
    settings: PacingSettings,
    total_duration: float = 60.0,
) -> list[CutPoint]:
    """Berechnet Schnittpunkte basierend auf Audio-BPM, Video-Szenen und Slider-Settings.

    Logik:
    - Beat-basierte Cuts: Aus BPM werden gleichmäßige Schnittpunkte abgeleitet.
      Der Tempo-Slider bestimmt, ob jeder Beat, jeder 2., 4. etc. ein Cut wird.
    - Szenen-basierte Cuts: Szenenübergänge aus der Video-Analyse.
    - Cut-Density filtert schwache Cuts heraus.
    """
    cuts: list[CutPoint] = []

    # ── Beat-basierte Cuts aus Audio-BPM ──────────────────────────────
    bpm = _get_bpm(audio_id)
    if bpm and bpm > 0:
        beat_interval = 60.0 / bpm  # Sekunden pro Beat

        # Tempo-Slider bestimmt den Beat-Divisor:
        # 0-25: jeder 4. Beat | 25-50: jeder 2. Beat |
        # 50-75: jeder Beat   | 75-100: jeder halbe Beat
        if settings.tempo < 25:
            divisor = 4
        elif settings.tempo < 50:
            divisor = 2
        elif settings.tempo < 75:
            divisor = 1
        else:
            divisor = 0.5

        cut_interval = beat_interval * divisor
        t = cut_interval  # Erster Cut nicht bei 0
        while t < total_duration:
            # Stärke basiert auf Energy-Slider
            strength = min(1.0, settings.energy / 100.0 + 0.3)
            cuts.append(CutPoint(time=round(t, 3), source="beat", strength=strength))
            t += cut_interval
    else:
        # Fallback ohne BPM: gleichmäßige Cuts basierend auf Tempo-Slider
        interval = max(1.0, 8.0 - (settings.tempo / 100.0 * 7.0))
        t = interval
        while t < total_duration:
            strength = min(1.0, settings.energy / 100.0 + 0.3)
            cuts.append(CutPoint(time=round(t, 3), source="energy", strength=strength))
            t += interval

    # ── Szenen-basierte Cuts aus Video ────────────────────────────────
    scenes = _get_scenes(video_id)
    for scene in scenes:
        cuts.append(CutPoint(
            time=round(scene.start_time, 3),
            source="scene",
            strength=min(1.0, (scene.energy or 0.5) + 0.2),
        ))

    # ── Filtern nach Cut-Density ──────────────────────────────────────
    # Höhere Density = niedrigere Schwelle = mehr Cuts bleiben
    threshold = 1.0 - (settings.cut_density / 100.0)
    cuts = [c for c in cuts if c.strength >= threshold]

    # Nach Zeit sortieren und Duplikate (< 0.1s Abstand) entfernen
    cuts.sort(key=lambda c: c.time)
    filtered: list[CutPoint] = []
    for cut in cuts:
        if not filtered or (cut.time - filtered[-1].time) >= 0.1:
            filtered.append(cut)

    return filtered


def _get_bpm(audio_id: int | None) -> float | None:
    """Holt BPM aus der DB für einen AudioTrack."""
    if audio_id is None:
        return None
    with Session(engine) as session:
        track = session.get(AudioTrack, audio_id)
        return track.bpm if track else None


def _get_scenes(video_id: int | None) -> list[Scene]:
    """Holt Szenen aus der DB für einen VideoClip."""
    if video_id is None:
        return []
    with Session(engine) as session:
        clip = session.get(VideoClip, video_id)
        if clip is None:
            return []
        # Eager-load damit wir außerhalb der Session zugreifen können
        return list(clip.scenes)
