"""Phase 3 Pacing-Service: DJ-Pacing Engine mit OTIO Timeline.

REGELN:
- Das Audio-File diktiert die Gesamtlaenge der OTIO Timeline.
- Jeder Schnitt faellt AUSNAHMSLOS auf einen Beat-Timestamp.
- Energy Reactivity moduliert die Cut-Rate basierend auf RMS-Energie.
- Breakdown Behavior aendert das Verhalten bei niedrigem RMS.
- Anker (OTIO Marker) werden respektiert und erzwingen bestimmte Videos.
- LanceDB Semantic Search fuer Keyword-Matching, sonst Motion/Random.
"""

import copy
import json
import logging
import random
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
from sqlalchemy.orm import Session
from database import engine, AudioTrack, VideoClip, Scene, Beatgrid, AIPacingMemory, TimelineEntry

logger = logging.getLogger(__name__)

# Sentinel value: step so hoch dass kein Cut stattfindet (breakdown_behavior="none")
_STEP_NO_CUT = 9999


def invalidate_pacing_caches():
    """Cache leeren nach Media-Import oder DB-Änderung."""
    _get_audio_duration.cache_clear()
    _get_audio_path.cache_clear()
    _get_bpm.cache_clear()
    _get_video_info_cached.cache_clear()


# ── Backward-compatible types ──

@dataclass
class PacingSettings:
    """Legacy UI-Slider-Einstellungen (Phase 2 compat)."""
    tempo: int = 50
    energy: int = 50
    cut_density: int = 50
    vibe: str = ""
    manual_density_curve: list[float] | None = None


@dataclass
class CutPoint:
    """Ein einzelner Schnittpunkt auf der Timeline."""
    time: float
    source: str       # "beat", "scene", "energy", "drum", "anchor"
    strength: float   # 0.0-1.0


# ── Phase 3: Advanced DJ Pacing ──

@dataclass
class AdvancedPacingSettings:
    """Phase 3 DJ-Regler Einstellungen."""
    base_cut_rate: int = 4          # 1, 2, 4, 8, 16 Beats
    energy_reactivity: int = 50     # 0-100%
    breakdown_behavior: str = "halve"  # "halve", "force16", "none"
    vibe: str = ""                  # Keyword fuer LanceDB Suche
    manual_density_curve: list[float] | None = None
    anchors: list[dict] | None = None  # [{"time": float, "scene_id": str}, ...]


@dataclass
class TimelineSegment:
    """Ein Segment auf der OTIO-Timeline."""
    video_id: int
    video_path: str
    start: float          # Timeline-Zeitpunkt (Sekunden)
    end: float            # Timeline-Zeitpunkt (Sekunden)
    source_start: float   # Quell-Video Offset (Sekunden)
    source_end: float     # Quell-Video Ende (Sekunden)
    is_anchor: bool = False
    scene_id: str = ""
    crossfade_duration: float = 0.0  # PhD-Spec: Crossfade per Section Type
    section_type: str = ""           # WARMUP/BUILDUP/DROP/BREAKDOWN/COOLDOWN


# ── Data Access ──

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



def _get_beat_data_combined(
    audio_id: int | None,
) -> tuple[list[float], list[float], list[float]]:
    """Laedt beat_positions, downbeat_positions und energy_per_beat in EINER Session.

    Bug-14 Fix: Kombiniert die drei separaten DB-Sessions (_get_beat_positions,
    _get_downbeat_positions, _get_energy_per_beat) in einen einzigen Round-Trip.
    Vorher: 3 Sessions für die gleiche AudioTrack/Beatgrid-Zeile.

    Returns: (beat_positions, downbeat_positions, energy_per_beat)
    """
    if audio_id is None:
        return [], [], []
    with Session(engine) as session:
        track = session.get(AudioTrack, audio_id)
        if not track or not track.beatgrid:
            return [], [], []
        bg = track.beatgrid

        # beat_positions (mit BPM-Fallback)
        beat_positions: list[float] = []
        if bg.beat_positions:
            try:
                beat_positions = [float(p) for p in json.loads(bg.beat_positions)]
            except (json.JSONDecodeError, TypeError):
                pass
        if not beat_positions and bg.bpm and bg.bpm > 0:
            interval = 60.0 / bg.bpm
            duration = track.duration or 300.0
            t = bg.offset or 0.0
            while t < duration:
                beat_positions.append(round(t, 4))
                t += interval

        # downbeat_positions
        downbeat_positions: list[float] = []
        if bg.downbeat_positions:
            try:
                downbeat_positions = [float(p) for p in json.loads(bg.downbeat_positions)]
            except (json.JSONDecodeError, TypeError):
                pass

        # energy_per_beat
        energy_per_beat: list[float] = []
        if bg.energy_per_beat:
            try:
                energy_per_beat = [float(e) for e in json.loads(bg.energy_per_beat)]
            except (json.JSONDecodeError, TypeError):
                pass

        return beat_positions, downbeat_positions, energy_per_beat


@lru_cache(maxsize=64)
def _get_audio_duration(audio_id: int) -> float:
    """Gibt die Dauer des Audio-Tracks in Sekunden zurueck."""
    with Session(engine) as session:
        track = session.get(AudioTrack, audio_id)
        return track.duration if track and track.duration else 60.0


@lru_cache(maxsize=64)
def _get_audio_path(audio_id: int) -> str:
    """Gibt den Dateipfad des Audio-Tracks zurueck."""
    with Session(engine) as session:
        track = session.get(AudioTrack, audio_id)
        return track.file_path if track else ""


@lru_cache(maxsize=64)
def _get_bpm(audio_id: int | None) -> float | None:
    if audio_id is None:
        return None
    with Session(engine) as session:
        track = session.get(AudioTrack, audio_id)
        return track.bpm if track else None


def _get_video_info(video_ids: list[int]) -> dict[int, dict]:
    """Holt Video-Metadaten (Dauer, Pfad) fuer alle IDs. Cached intern."""
    return copy.deepcopy(_get_video_info_cached(tuple(sorted(video_ids))))


@lru_cache(maxsize=32)
def _get_video_info_cached(video_ids: tuple[int, ...]) -> dict[int, dict]:
    """Cached-Backend fuer _get_video_info (tuple ist hashable)."""
    info = {}
    if not video_ids:
        return info
    with Session(engine) as session:
        clips = session.query(VideoClip).filter(VideoClip.id.in_(video_ids)).all()
        for clip in clips:
            info[clip.id] = {
                "duration": clip.duration or 10.0,
                "path": clip.file_path,
                "scenes": [
                    {"start": s.start_time, "end": s.end_time,
                     "energy": s.energy or 0.5, "id": s.id}
                    for s in clip.scenes
                ],
            }
    return info


def _get_scenes(video_id: int | None) -> list[dict]:
    """Laedt Scenes als Dicts (nicht ORM-Objekte) um DetachedInstanceError zu vermeiden."""
    if video_id is None:
        return []
    with Session(engine) as session:
        clip = session.get(VideoClip, video_id)
        if clip is None:
            return []
        # P2-07: Dicts statt ORM-Objekte zurueckgeben (Session wird geschlossen)
        return [{"id": s.id, "start_time": s.start_time, "end_time": s.end_time,
                 "energy": s.energy or 0.5, "video_clip_id": s.video_clip_id}
                for s in clip.scenes]


# ======================================================================
# PhD-Level Features: Stem-Weighted Energy, Section Detection, Vocal-Aware
# ======================================================================

@dataclass
class StemEnergy:
    """Per-Beat Energie aus den individuellen Demucs-Stems."""
    drums: list[float]     # RMS pro Beat (0.0-1.0)
    bass: list[float]
    vocals: list[float]
    other: list[float]
    weighted: list[float]  # Gewichtete Kombination


def compute_stem_weighted_energy(
    audio_id: int,
    beats: list[float],
    w_drums: float = 0.40,
    w_bass: float = 0.30,
    w_vocals: float = 0.10,
    w_other: float = 0.20,
) -> StemEnergy | None:
    """F-004: Berechnet per-Beat RMS-Energie aus den individuellen Demucs-Stems.

    PhD-Spec Abschnitt 3.3:
      E_weighted(t) = w_drums * E_drums(t) + w_bass * E_bass(t)
                    + w_vocals * E_vocals(t) + w_other * E_other(t)

    Faellt auf die Stereo-Summe zurueck wenn Stems nicht vorhanden sind.
    """
    with Session(engine) as session:
        track = session.get(AudioTrack, audio_id)
        if not track:
            return None
        stem_paths = {
            "drums": track.stem_drums_path,
            "bass": track.stem_bass_path,
            "vocals": track.stem_vocals_path,
            "other": track.stem_other_path,
        }

    # Pruefen ob mindestens ein Stem vorhanden ist
    available = {k: v for k, v in stem_paths.items() if v and Path(v).exists()}
    if not available:
        logger.info("Keine Stems fuer Audio %d — Fallback auf Stereo-Summe", audio_id)
        return None

    if not beats or len(beats) < 2:
        return None

    try:
        import librosa
    except ImportError:
        logger.warning("librosa nicht verfuegbar fuer Stem-Energie-Berechnung")
        return None

    def _compute_rms_per_beat(audio_path: str, beats_list: list[float]) -> list[float]:
        """Berechnet RMS pro Beat-Intervall fuer eine einzelne Stem-Datei.

        M7 Fix: Laedt nur den benoetigten Zeitbereich (beats[0]..beats[-1] + Buffer)
        statt die komplette Stem-Datei in RAM.
        """
        # Bestimme den benoetigten Zeitbereich mit 1s Buffer
        load_offset = max(0.0, beats_list[0] - 1.0)
        load_end = beats_list[-1] + 1.0  # 1s Buffer nach dem letzten Beat
        load_duration = load_end - load_offset

        try:
            y, sr = librosa.load(audio_path, sr=22050, mono=True,
                                 offset=load_offset, duration=load_duration)
        except Exception as e:
            logger.warning("Konnte Stem '%s' nicht laden: %s", audio_path, e)
            return [0.5] * len(beats_list)

        audio_duration = len(y) / sr
        energies = []
        for i in range(len(beats_list)):
            start_sec = beats_list[i] - load_offset  # Relativ zum geladenen Bereich
            end_sec = (beats_list[i + 1] - load_offset) if i + 1 < len(beats_list) else audio_duration
            start_sample = int(start_sec * sr)
            end_sample = min(int(end_sec * sr), len(y))
            if start_sample >= end_sample or start_sample < 0:
                energies.append(0.0)
                continue
            seg = y[start_sample:end_sample]
            rms = float(np.sqrt(np.mean(seg ** 2)))
            energies.append(rms)

        # Normalisiere auf [0, 1]
        max_e = max(energies) if energies else 1.0
        if max_e > 0:
            energies = [e / max_e for e in energies]
        return energies

    weights = {"drums": w_drums, "bass": w_bass, "vocals": w_vocals, "other": w_other}
    stem_energies: dict[str, list[float]] = {}
    default_energy = [0.5] * len(beats)

    for stem_name in ["drums", "bass", "vocals", "other"]:
        if stem_name in available:
            stem_energies[stem_name] = _compute_rms_per_beat(available[stem_name], beats)
        else:
            stem_energies[stem_name] = default_energy

    # Gewichtete Kombination
    weighted = []
    for i in range(len(beats)):
        w_sum = 0.0
        for stem_name, w in weights.items():
            w_sum += w * stem_energies[stem_name][i]
        weighted.append(round(min(1.0, w_sum), 4))

    logger.info(
        "Stem-gewichtete Energie berechnet: %d Beats, Stems=%s",
        len(beats), list(available.keys()),
    )

    return StemEnergy(
        drums=stem_energies["drums"],
        bass=stem_energies["bass"],
        vocals=stem_energies["vocals"],
        other=stem_energies["other"],
        weighted=weighted,
    )


@dataclass
class Section:
    """Eine erkannte Makro-Sektion im DJ-Set."""
    start: float          # Startzeit in Sekunden
    end: float            # Endzeit in Sekunden
    section_type: str     # WARMUP, BUILDUP, DROP, BREAKDOWN, TRANSITION, COOLDOWN
    avg_energy: float     # Mittlere Energie in der Sektion


def detect_sections(
    energy_per_beat: list[float],
    beats: list[float],
    total_duration: float,
    window_beats: int = 32,
    min_section_beats: int = 64,
) -> list[Section]:
    """F-005: Erkennt Makro-Sektionen in einem DJ-Set.

    PhD-Spec Abschnitt 2.2: Adaptive Section Detection.

    Methode: Gleitender Mittelwert mit Hysterese.
    Section Types:
      WARMUP:     Erste 5% der Dauer, Energie < 0.5
      BUILDUP:    Energie steigt monoton ueber min_section_beats
      DROP:       Energie > 0.7 fuer min_section_beats/2
      BREAKDOWN:  Energie < 0.3 fuer min_section_beats/2
      TRANSITION: Wechsel zwischen Sektionstypen
      COOLDOWN:   Letzte 5% der Dauer, Energie fallend
    """
    if not energy_per_beat or not beats or len(beats) < window_beats:
        return [Section(start=0.0, end=total_duration, section_type="TRANSITION",
                        avg_energy=0.5)]

    n = len(energy_per_beat)
    energy_arr = np.array(energy_per_beat[:n])

    # 1. Gleitender Mittelwert (Fenster = window_beats)
    kernel = np.ones(window_beats) / window_beats
    smoothed = np.convolve(energy_arr, kernel, mode='same')

    # 2. Gradient (Steigung der Energiekurve)
    gradient = np.gradient(smoothed)

    # 3. Sektionsklassifikation pro Beat
    beat_labels = []
    warmup_end = int(n * 0.05)
    cooldown_start = int(n * 0.95)

    for i in range(n):
        avg_e = float(smoothed[i])
        avg_g = float(gradient[i])

        if i < warmup_end and avg_e < 0.5:
            beat_labels.append("WARMUP")
        elif i >= cooldown_start and avg_g < -0.001:
            beat_labels.append("COOLDOWN")
        elif avg_e > 0.7:
            beat_labels.append("DROP")
        elif avg_e < 0.3:
            beat_labels.append("BREAKDOWN")
        elif avg_g > 0.002:
            beat_labels.append("BUILDUP")
        elif avg_g < -0.002:
            beat_labels.append("TRANSITION")
        else:
            beat_labels.append("TRANSITION")

    # 4. Zusammenfassen zu Sektionen (gleiche Labels zusammenhaengen)
    sections: list[Section] = []
    current_type = beat_labels[0]
    section_start_idx = 0

    for i in range(1, n):
        if beat_labels[i] != current_type:
            # Sektion abschliessen
            start_time = beats[section_start_idx] if section_start_idx < len(beats) else 0.0
            end_time = beats[i] if i < len(beats) else total_duration
            avg_e = float(np.mean(energy_arr[section_start_idx:i]))
            sections.append(Section(
                start=round(start_time, 2),
                end=round(end_time, 2),
                section_type=current_type,
                avg_energy=round(avg_e, 3),
            ))
            current_type = beat_labels[i]
            section_start_idx = i

    # Letzte Sektion
    start_time = beats[section_start_idx] if section_start_idx < len(beats) else 0.0
    avg_e = float(np.mean(energy_arr[section_start_idx:]))
    sections.append(Section(
        start=round(start_time, 2),
        end=round(total_duration, 2),
        section_type=current_type,
        avg_energy=round(avg_e, 3),
    ))

    # 5. Zu kurze Sektionen mit Nachbarn verschmelzen
    merged: list[Section] = []
    for sec in sections:
        sec_beats = 0
        if beats:
            sec_beats = sum(1 for b in beats if sec.start <= b < sec.end)

        if merged and sec_beats < min_section_beats // 2:
            # Zu kurz — mit vorheriger Sektion verschmelzen
            merged[-1] = Section(
                start=merged[-1].start,
                end=sec.end,
                section_type=merged[-1].section_type,
                avg_energy=round((merged[-1].avg_energy + sec.avg_energy) / 2, 3),
            )
        else:
            merged.append(sec)

    logger.info("Makro-Struktur erkannt: %d Sektionen in %.0fs",
                len(merged), total_duration)
    for s in merged:
        logger.debug("  [%s] %.1fs - %.1fs (avg_energy=%.2f)",
                     s.section_type, s.start, s.end, s.avg_energy)

    return merged


def get_section_at_time(sections: list[Section], time: float) -> Section | None:
    """Findet die Sektion die einen bestimmten Zeitpunkt enthaelt."""
    for sec in sections:
        if sec.start <= time < sec.end:
            return sec
    return sections[-1] if sections else None


def compute_vocal_activity(
    audio_id: int,
    beats: list[float],
    threshold: float = 0.15,
) -> list[bool]:
    """F-009: Berechnet pro Beat ob Vocals aktiv sind.

    PhD-Spec Abschnitt 7.3: Vocal-Aware Pacing.
    Wenn vocal_rms > threshold: Vocal aktiv → weniger Schnitte.

    Returns: Liste von booleans, True = Vocals aktiv bei diesem Beat.
    """
    with Session(engine) as session:
        track = session.get(AudioTrack, audio_id)
        if not track or not track.stem_vocals_path:
            return [False] * len(beats)
        vocals_path = track.stem_vocals_path

    if not Path(vocals_path).exists():
        return [False] * len(beats)

    if not beats or len(beats) < 2:
        return [False] * len(beats)

    try:
        import librosa
        # M7 Fix: Nur den benoetigten Zeitbereich laden statt kompletten Stem
        load_offset = max(0.0, beats[0] - 1.0)
        load_end = beats[-1] + 1.0  # 1s Buffer nach dem letzten Beat
        load_duration = load_end - load_offset
        y, sr = librosa.load(vocals_path, sr=22050, mono=True,
                             offset=load_offset, duration=load_duration)
    except Exception as e:
        logger.warning("Konnte Vocal-Stem '%s' nicht laden: %s", vocals_path, e)
        return [False] * len(beats)

    audio_duration = len(y) / sr
    activity = []
    for i in range(len(beats)):
        start_sec = beats[i] - load_offset  # Relativ zum geladenen Bereich
        end_sec = (beats[i + 1] - load_offset) if i + 1 < len(beats) else audio_duration
        start_sample = int(start_sec * sr)
        end_sample = min(int(end_sec * sr), len(y))
        if start_sample >= end_sample or start_sample < 0:
            activity.append(False)
            continue
        seg = y[start_sample:end_sample]
        rms = float(np.sqrt(np.mean(seg ** 2)))
        activity.append(rms > threshold)

    vocal_beats = sum(activity)
    logger.info("Vocal-Activity: %d/%d Beats mit Vocals (%.0f%%)",
                vocal_beats, len(beats), 100.0 * vocal_beats / max(len(beats), 1))
    return activity


@dataclass
class DropEvent:
    """Ein erkannter Drop im DJ-Set."""
    time: float           # Beat-Zeitpunkt des Drops (Sekunden)
    confidence: float     # 0.0-1.0 (Stärke des RMS-Sprungs)
    energy_before: float  # Durchschnittliche Bass-Energie VOR dem Drop
    energy_after: float   # Bass-Energie NACH dem Drop


def detect_drops(
    stem_energy: StemEnergy | None,
    energy_per_beat: list[float],
    beats: list[float],
    pre_threshold: float = 0.2,
    post_threshold: float = 0.6,
    lookback_beats: int = 8,
) -> list[DropEvent]:
    """PhD-Spec Abschnitt 8: Multi-Stem Drop-Detektion via Bass-Stem.

    Ein Drop ist definiert als:
      - Bass-RMS vorher < pre_threshold fuer lookback_beats (Breakdown/Buildup)
      - Bass-RMS nachher > post_threshold (ploetzliche hohe Energie)

    Wenn Stems vorhanden: Nutze bass-Stem. Sonst: Stereo-Summe als Fallback.
    """
    # Waehle die beste Energiequelle
    bass_energy = stem_energy.bass if stem_energy else energy_per_beat
    if not bass_energy or not beats:
        return []

    if len(beats) < 2:
        return []

    drops: list[DropEvent] = []
    n = len(bass_energy)

    for i in range(lookback_beats, n):
        prev_avg = float(np.mean(bass_energy[max(0, i - lookback_beats):i]))
        curr = float(bass_energy[i])

        if prev_avg < pre_threshold and curr > post_threshold:
            beat_time = beats[i] if i < len(beats) else 0.0
            confidence = min(1.0, (curr - prev_avg) * 1.5)

            # Dedupliziere: kein zweiter Drop innerhalb von 16 Beats
            if drops and i < len(beats):
                last_drop_time = drops[-1].time
                if beat_time - last_drop_time < 16 * (beats[1] - beats[0] if len(beats) > 1 else 0.5):
                    continue

            drops.append(DropEvent(
                time=round(beat_time, 2),
                confidence=round(confidence, 3),
                energy_before=round(prev_avg, 3),
                energy_after=round(curr, 3),
            ))

    logger.info("Drop-Detektion: %d Drops erkannt", len(drops))
    for d in drops:
        logger.debug("  Drop bei %.1fs (confidence=%.2f, before=%.2f, after=%.2f)",
                     d.time, d.confidence, d.energy_before, d.energy_after)
    return drops


# PhD-Spec Abschnitt 2.3: Section → Crossfade-Dauer Mapping
SECTION_CROSSFADE_MAP: dict[str, float] = {
    "WARMUP":     2.0,   # Soft crossfade
    "BUILDUP":    1.0,   # Crossfade → Hard cut
    "DROP":       0.0,   # Hard cut (0ms)
    "BREAKDOWN":  3.0,   # Slow dissolve
    "TRANSITION": 1.5,   # Medium crossfade
    "COOLDOWN":   4.0,   # Long dissolve
}


def section_to_crossfade(section_type: str) -> float:
    """PhD-Spec Abschnitt 2.3: Bestimmt die Crossfade-Dauer basierend auf der Sektion."""
    return SECTION_CROSSFADE_MAP.get(section_type, 0.0)


def detect_transitions(
    stem_energy: StemEnergy | None,
    energy_per_beat: list[float],
    beats: list[float],
    min_transition_beats: int = 32,
) -> list[tuple[float, float]]:
    """PhD-Spec Abschnitt 9: DJ-Übergangs-Erkennung.

    Ein DJ-Übergang wird erkannt durch:
    - Drum-Stem-Anomalie: Onset-Dichte verdoppelt sich (zwei Kicks überlagern)
    - Oder: Energie-Gradient wechselt Vorzeichen mit mittlerer Amplitude

    Returns: Liste von (start_time, end_time) Tupeln fuer erkannte Übergänge.
    """
    if not energy_per_beat or not beats or len(beats) < min_transition_beats * 2:
        return []

    # Nutze Drum-Energie wenn verfuegbar, sonst Stereo-Summe
    drum_energy = stem_energy.drums if stem_energy else energy_per_beat
    n = len(drum_energy)

    # Gleitender Mittelwert der Drum-Energie (16 Beats)
    window = min(16, n // 2)
    if window < 4:
        return []
    kernel = np.ones(window) / window
    smoothed = np.convolve(np.array(drum_energy[:n]), kernel, mode='same')

    # Berechne lokale Varianz (hohe Varianz = zwei Tracks ueberlagern sich)
    variance = np.convolve((np.array(drum_energy[:n]) - smoothed) ** 2, kernel, mode='same')

    # Normalisiere
    max_var = float(np.max(variance)) if np.max(variance) > 0 else 1.0
    norm_var = variance / max_var

    # Finde Bereiche mit hoher Varianz (> 0.5) die mindestens min_transition_beats lang sind
    transitions: list[tuple[float, float]] = []
    in_transition = False
    trans_start_idx = 0

    for i in range(n):
        if norm_var[i] > 0.5 and not in_transition:
            in_transition = True
            trans_start_idx = i
        elif (norm_var[i] <= 0.5 or i == n - 1) and in_transition:
            in_transition = False
            duration_beats = i - trans_start_idx
            if duration_beats >= min_transition_beats:
                start_time = beats[trans_start_idx] if trans_start_idx < len(beats) else 0.0
                end_time = beats[min(i, len(beats) - 1)]
                transitions.append((round(start_time, 2), round(end_time, 2)))

    logger.info("Transition-Detektion: %d DJ-Uebergaenge erkannt", len(transitions))
    return transitions


# ── Legacy Phase 2 functions (kept for backward compat) ──

def _density_to_beat_step(density: float) -> int:
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
    """Phase 2 compat: Berechnet Schnittpunkte EXAKT auf Beat-Timestamps."""
    beats = _get_beat_positions(audio_id)
    cuts: list[CutPoint] = []

    if beats:
        if settings.tempo >= 80:
            base_step = 1
        elif settings.tempo >= 60:
            base_step = 2
        elif settings.tempo >= 40:
            base_step = 4
        elif settings.tempo >= 20:
            base_step = 8
        else:
            base_step = 16

        curve = settings.manual_density_curve
        num_curve_samples = len(curve) if curve else 0

        for i, beat_time in enumerate(beats):
            if beat_time >= total_duration:
                break
            if curve and num_curve_samples > 0:
                curve_idx = int((beat_time / max(total_duration, 1e-9)) * (num_curve_samples - 1))
                curve_idx = max(0, min(curve_idx, num_curve_samples - 1))
                density = curve[curve_idx]
                curve_step = _density_to_beat_step(density)
                effective_step = min(base_step, curve_step) if density >= 0.5 else max(base_step, curve_step)
            else:
                effective_step = base_step

            if i % effective_step == 0:
                strength = min(1.0, settings.energy / 100.0 + 0.3)
                if i % 4 == 0:
                    strength = min(1.0, strength + 0.15)
                cuts.append(CutPoint(
                    time=round(beat_time, 4), source="beat", strength=round(strength, 3),
                ))
    else:
        bpm = _get_bpm(audio_id)
        if bpm and bpm > 0:
            interval = 60.0 / bpm
            t, i = 0.0, 0
            while t < total_duration:
                strength = min(1.0, settings.energy / 100.0 + 0.3)
                if i % 4 == 0:
                    strength = min(1.0, strength + 0.15)
                cuts.append(CutPoint(time=round(t, 3), source="beat", strength=strength))
                t += interval
                i += 1
        else:
            interval = max(1.0, 8.0 - (settings.tempo / 100.0 * 7.0))
            t = interval
            while t < total_duration:
                strength = min(1.0, settings.energy / 100.0 + 0.3)
                cuts.append(CutPoint(time=round(t, 3), source="energy", strength=strength))
                t += interval

    scenes = _get_scenes(video_id)
    if beats and scenes:
        beats_arr = np.array(beats)
        # O(N log N): Existierende Cut-Zeiten als sortiertes Array für schnelle Duplikat-Prüfung
        cut_times = np.array(sorted(c.time for c in cuts)) if cuts else np.array([])
        for scene in scenes:
            idx = np.searchsorted(beats_arr, scene["start_time"])
            if idx < len(beats_arr):
                snapped = float(beats_arr[idx])
                # Binary search statt linearem any()
                pos = np.searchsorted(cut_times, snapped)
                is_dup = False
                for check in (pos - 1, pos):
                    if 0 <= check < len(cut_times) and abs(cut_times[check] - snapped) < 0.05:
                        is_dup = True
                        break
                if not is_dup:
                    new_cut = CutPoint(
                        time=round(snapped, 4), source="scene",
                        strength=min(1.0, (scene["energy"] or 0.5) + 0.2),
                    )
                    cuts.append(new_cut)
                    # cut_times aktuell halten für nächste Iteration
                    ins = np.searchsorted(cut_times, snapped)
                    cut_times = np.insert(cut_times, ins, snapped)

    threshold = 1.0 - (settings.cut_density / 100.0)
    cuts = [c for c in cuts if c.strength >= threshold]
    cuts.sort(key=lambda c: c.time)
    filtered: list[CutPoint] = []
    for cut in cuts:
        if not filtered or (cut.time - filtered[-1].time) >= 0.1:
            filtered.append(cut)
    return filtered


def calculate_drum_cuts(audio_id: int, total_duration: float = 60.0,
                        energy_threshold: float = 0.3) -> list[CutPoint]:
    """Berechnet Schnittpunkte basierend auf dem Drums-Stem."""
    with Session(engine) as session:
        track = session.get(AudioTrack, audio_id)
        if not track or not track.stem_drums_path:
            return []
        drums_path = track.stem_drums_path
    try:
        import librosa
        y, sr = librosa.load(drums_path, sr=22050, mono=True)
    except Exception as e:
        logger.warning("librosa.load fehlgeschlagen für Drums-Stem '%s': %s", drums_path, e)
        return []
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onset_frames = librosa.onset.onset_detect(
        onset_envelope=onset_env, sr=sr, backtrack=False
    )
    onset_times = librosa.frames_to_time(onset_frames, sr=sr)
    beats = _get_beat_positions(audio_id)
    beats_arr = np.array(beats) if beats else None
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
            if beats_arr is not None and len(beats_arr) > 0:
                idx = np.argmin(np.abs(beats_arr - onset_time))
                snapped_time = float(beats_arr[idx])
                if abs(snapped_time - onset_time) <= 0.15 and snapped_time not in used_beats:
                    used_beats.add(snapped_time)
                    cuts.append(CutPoint(
                        time=round(snapped_time, 4), source="drum",
                        strength=round(strength, 3),
                    ))
            else:
                cuts.append(CutPoint(
                    time=round(float(onset_time), 3), source="drum",
                    strength=round(strength, 3),
                ))
    return cuts


# ======================================================================
# Phase 3: Advanced DJ Pacing Engine
# ======================================================================

def _compute_effective_step(
    base_step: int,
    beat_index: int,
    beat_time: float,
    total_duration: float,
    energy_per_beat: list[float],
    energy_reactivity: float,
    breakdown_behavior: str,
    pacing_curve: list[float] | None,
    avg_motion: float = 0.5,
    vocal_active: bool = False,
) -> int:
    """Berechnet den effektiven Beat-Schritt fuer einen bestimmten Beat.

    Kombiniert:
    - base_cut_rate (aus UI)
    - energy_reactivity (erhoeht Cuts bei hohem RMS)
    - breakdown_behavior (reduziert Cuts bei niedrigem RMS)
    - manual_density_curve (optionale Ueberschreibung)
    - avg_motion (RAFT Motion-Score, PhD-Spec Schritt 3)
    - vocal_active (PhD-Spec: S_eff x 2 bei aktiven Vocals)
    """
    effective = base_step

    # 1. Pacing-Kurve (wenn vorhanden, hat hoechste Prioritaet)
    if pacing_curve and len(pacing_curve) > 0:
        curve_idx = int((beat_time / max(total_duration, 0.1)) * (len(pacing_curve) - 1))
        curve_idx = max(0, min(curve_idx, len(pacing_curve) - 1))
        density = pacing_curve[curve_idx]
        curve_step = _density_to_beat_step(density)
        # Mische Kurve mit Base: bei hoher Dichte kuerzeren Step
        if density >= 0.5:
            effective = min(base_step, curve_step)
        else:
            effective = max(base_step, curve_step)

    # 2. Energy Reactivity
    reactivity = energy_reactivity / 100.0
    energy = 0.5
    if reactivity > 0 and beat_index < len(energy_per_beat):
        energy = energy_per_beat[beat_index]

        # Hohe Energie (>0.7): Step reduzieren (mehr Cuts)
        if energy > 0.7:
            speed_boost = 1.0 + (energy - 0.7) * 3.0 * reactivity  # max ~1.9x
            effective = max(1, int(effective / speed_boost))

        # Niedrige Energie (<0.3): Breakdown-Verhalten anwenden
        elif energy < 0.3:
            if breakdown_behavior == "halve":
                effective = min(16, effective * 2)
            elif breakdown_behavior == "force16":
                effective = 16
            elif breakdown_behavior == "none":
                effective = _STEP_NO_CUT

        # Mittlere Energie (0.3-0.7): Leichte Modulation
        elif 0.3 <= energy <= 0.5:
            # Leicht verlangsamen bei niedrig-mittel
            effective = min(16, int(effective * 1.5))

    # Guard: "none" = kein Cut, Motion-Adjustment nicht anwenden
    if effective >= _STEP_NO_CUT:
        return effective

    # 3. Motion-Adjusted Step (PhD-Spec Schritt 3: combined_intensity)
    # Kombiniert Audio-Energie mit Video-Motion-Score
    combined_intensity = energy * 0.6 + avg_motion * 0.4
    if combined_intensity >= 0.8:
        effective = max(1, effective // 4)
    elif combined_intensity >= 0.6:
        effective = max(1, effective // 2)
    elif combined_intensity < 0.2:
        effective = min(16, effective * 4)
    elif combined_intensity < 0.4:
        effective = min(16, effective * 2)
    # 0.4-0.6: No change (normal)

    # 4. Vocal-Aware Pacing (PhD-Spec Abschnitt 7.3)
    # Wenn Vocals aktiv: Schnittfrequenz halbieren fuer visuelle Stabilitaet
    if vocal_active:
        effective = min(16, effective * 2)

    return max(1, effective)


def _select_cut_beats_advanced(
    beats: list[float],
    total_duration: float,
    settings: AdvancedPacingSettings,
    energy_per_beat: list[float],
    avg_motion: float = 0.5,
    vocal_activity: list[bool] | None = None,
) -> list[float]:
    """Phase 3: Waehlt Cut-Beats basierend auf DJ-Reglern aus."""
    if not beats:
        return []

    selected: list[float] = []
    beats_since_last_cut = 0

    for i, beat_time in enumerate(beats):
        if beat_time >= total_duration:
            break

        is_vocal = vocal_activity[i] if vocal_activity and i < len(vocal_activity) else False

        step = _compute_effective_step(
            base_step=settings.base_cut_rate,
            beat_index=i,
            beat_time=beat_time,
            total_duration=total_duration,
            energy_per_beat=energy_per_beat,
            energy_reactivity=settings.energy_reactivity,
            breakdown_behavior=settings.breakdown_behavior,
            pacing_curve=settings.manual_density_curve,
            avg_motion=avg_motion,
            vocal_active=is_vocal,
        )

        beats_since_last_cut += 1
        if beats_since_last_cut >= step:
            selected.append(beat_time)
            beats_since_last_cut = 0

    return selected


def _match_video_for_segment(
    seg_start: float,
    seg_end: float,
    vibe: str,
    video_info: dict[int, dict],
    available_ids: list[int],
    clip_offsets: dict[int, float],
    used_recently: list[int],
    energy_per_beat: list[float] | None = None,
    beats: list[float] | None = None,
    memory_bias: dict | None = None,
) -> tuple[int, float]:
    """Waehlt den besten Video-Clip fuer ein Segment.

    Bei Vibe-Keyword: LanceDB Semantic Search.
    Sonst: Motion-Score oder Round-Robin mit Varianz.

    Returns: (video_id, source_start)
    """
    # LanceDB Semantic Search bei Vibe-Keyword
    if vibe and vibe.strip():
        try:
            from services.video_analysis_service import search_videos_by_text
            results = search_videos_by_text(vibe.strip(), top_k=5)
            if results:
                # Finde Video-ID aus dem Suchergebnis
                for r in results:
                    r_path = r.get("video_path", "")
                    for vid, info in video_info.items():
                        if info["path"] == r_path:
                            scene_start = r.get("scene_start", 0.0)
                            return vid, scene_start
        except Exception as e:
            logger.warning("LanceDB Suche fehlgeschlagen: %s", e)

    # Fallback: Motion-basiertes Matching
    # Berechne echte Audio-Energie fuer den Segment-Mittelpunkt
    energy_value = 0.5  # Default
    if energy_per_beat and beats:
        seg_mid = (seg_start + seg_end) / 2.0
        beat_idx = int(np.searchsorted(np.array(beats), seg_mid))
        beat_idx = min(beat_idx, len(energy_per_beat) - 1)
        if beat_idx >= 0:
            energy_value = energy_per_beat[beat_idx]

    # KI-Gedaechtnis: Preferred motion aus Lern-Beispielen einfliessen lassen
    if memory_bias is not None:
        pref_motion = memory_bias.get("preferred_motion")
        if pref_motion is not None:
            # 40% Gewicht auf gelernte Praeferenz (nicht ueberwiegend, da Audio-Energie Prio hat)
            energy_value = energy_value * 0.6 + pref_motion * 0.4

    vid, source_start = _match_video_by_motion(
        energy_value, video_info, available_ids, used_recently,
    )
    # Fallback source_start aus clip_offsets wenn kein Scene-Match
    if source_start == 0.0:
        source_start = clip_offsets.get(vid, 0.0)
    return vid, source_start


def auto_edit_phase3(
    audio_id: int,
    video_clip_ids: list[int],
    settings: AdvancedPacingSettings,
    progress_cb=None,
) -> tuple[list[TimelineSegment], list[CutPoint]]:
    """Phase 3: DJ-Pacing Engine — OTIO-konforme Timeline-Generierung.

    ZWINGENDE REGEL: Das Audio-File diktiert die Gesamtlaenge der Timeline.

    Returns:
        (segments, cut_points) — Segmente fuer OTIO + CutPoints fuer UI-Visualisierung
    """
    # 1. Audio-Dauer = Timeline-Laenge
    if progress_cb:
        progress_cb(0, "Lade Audio-Daten...")
    total_duration = _get_audio_duration(audio_id)
    logger.info("Phase 3 Auto-Edit: Audio-Dauer = %.1fs", total_duration)

    # 2. Beats + Downbeats + Energie laden
    # Bug-14 Fix: _get_beat_data_combined() öffnet nur EINE Session statt 3
    beats, downbeats, energy_per_beat = _get_beat_data_combined(audio_id)

    # Fallback: Beats aus BPM generieren
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
        return [], []

    if progress_cb:
        progress_cb(20, "Lade Video-Metadaten...")
    # 3. Video-Info laden
    video_info = _get_video_info(video_clip_ids)
    if not video_info:
        return [], []

    # 4. Anker sammeln (erzwungene Video-Zuweisungen)
    anchors = settings.anchors or []
    anchor_times = {a["time"]: a for a in anchors}

    if progress_cb:
        progress_cb(30, "Analysiere Stems und Motion...")

    # F-004: Stem-gewichtete Energie (ersetzt Stereo-Summe wenn Stems vorhanden)
    stem_energy = compute_stem_weighted_energy(audio_id, beats)
    if stem_energy is not None:
        energy_per_beat = stem_energy.weighted
        logger.info("Nutze Stem-gewichtete Energie statt Stereo-Summe")

    # F-005: Makro-Sektionserkennung
    sections = detect_sections(energy_per_beat, beats, total_duration)
    logger.info("Erkannte Sektionen: %s",
                [(s.section_type, f"{s.start:.0f}-{s.end:.0f}s") for s in sections])

    # F-009: Vocal-Activity fuer Vocal-Aware Pacing
    vocal_activity = compute_vocal_activity(audio_id, beats)

    # PhD-Spec Abschnitt 8: Drop-Detection via Bass-Stem
    drops = detect_drops(stem_energy, energy_per_beat, beats)
    drop_times = {d.time for d in drops}

    if progress_cb:
        progress_cb(40, "Berechne Cut-Beats...")

    # Berechne durchschnittlichen Motion-Score aller Szenen (PhD-Spec Schritt 3)
    total_motion = 0.0
    motion_count = 0
    for vid_data in video_info.values():
        for scene in vid_data.get("scenes", []):
            total_motion += scene.get("energy", 0.5)
            motion_count += 1
    avg_motion = total_motion / motion_count if motion_count > 0 else 0.5

    # KI-Gedaechtnis: Aehnliche Audio-Situationen aus Lern-Beispielen abrufen
    avg_energy_val = float(np.mean(energy_per_beat)) if energy_per_beat else 0.5
    bpm_val = _get_bpm(audio_id) or 120.0
    memory_bias = _get_ai_memory_bias(bpm_val, avg_energy_val)
    if memory_bias:
        # Preferred motion aus Gedaechtnis in avg_motion einfliessen lassen (30% Gewicht)
        pref_motion = memory_bias.get("preferred_motion")
        if pref_motion is not None:
            avg_motion = avg_motion * 0.7 + pref_motion * 0.3
            logger.info(
                "AI Memory: avg_motion angepasst auf %.3f (Lernregel: '%s')",
                avg_motion, memory_bias.get("label", ""),
            )

    # DJ-Mix Transition-Erkennung (PhD-Spec Abschnitt 9)
    transitions = detect_transitions(stem_energy, energy_per_beat, beats)
    transition_ranges = [(t[0], t[1]) for t in transitions]
    if transitions:
        logger.info("DJ-Uebergaenge erkannt: %s",
                    [(f"{s:.0f}-{e:.0f}s") for s, e in transition_ranges])

    # 5. Cut-Beats berechnen (Phase 3 mit Motion-Fusion + Vocal-Awareness)
    cut_beats = _select_cut_beats_advanced(
        beats, total_duration, settings, energy_per_beat,
        avg_motion=avg_motion,
        vocal_activity=vocal_activity,
    )

    # Start immer bei 0
    if not cut_beats or cut_beats[0] > 0.01:
        cut_beats.insert(0, 0.0)
    # Ende = Audio-Dauer
    if cut_beats[-1] < total_duration - 0.1:
        cut_beats.append(total_duration)

    # Anker-Zeitpunkte einfuegen (auf naechsten Beat snappen)
    beats_arr = np.array(beats)
    for anchor_time in (anchor_times if beats_arr.size > 0 else []):
        idx = np.argmin(np.abs(beats_arr - anchor_time))
        snapped = float(beats_arr[idx])
        if not any(abs(cb - snapped) < 0.05 for cb in cut_beats):
            cut_beats.append(snapped)
    cut_beats.sort()

    if progress_cb:
        progress_cb(60, "Erzeuge Timeline-Segmente...")
    # 6. Segmente erzeugen
    segments: list[TimelineSegment] = []
    cut_points: list[CutPoint] = []
    available_ids = [vid for vid in video_clip_ids if vid in video_info]
    if not available_ids:
        return [], []

    clip_offsets: dict[int, float] = {vid: 0.0 for vid in available_ids}
    used_recently: list[int] = []

    # Pre-resolve anchor scenes to avoid DB session per segment
    anchor_scene_map: dict[str, int] = {}  # scene_id_str -> video_clip_id
    if anchor_times:
        scene_ids = []
        for anchor_data in anchor_times.values():
            sid = anchor_data.get("scene_id", "")
            if sid:
                try:
                    scene_ids.append(int(sid))
                except (ValueError, TypeError):
                    pass
        if scene_ids:
            with Session(engine) as session:
                for scene in session.query(Scene).filter(Scene.id.in_(scene_ids)).all():
                    anchor_scene_map[str(scene.id)] = scene.video_clip_id

    for i in range(len(cut_beats) - 1):
        seg_start = cut_beats[i]
        seg_end = cut_beats[i + 1]
        seg_duration = seg_end - seg_start

        if seg_duration < 0.1:
            continue

        # Pruefen ob ein Anker dieses Segment erzwingt
        is_anchor = False
        anchor_scene_id = ""
        anchor_vid = None

        for anchor_time, anchor_data in anchor_times.items():
            if abs(seg_start - anchor_time) < 0.5 or (seg_start <= anchor_time < seg_end):
                is_anchor = True
                anchor_scene_id = anchor_data.get("scene_id", "")
                # Scene-ID zu Video-ID aufloesen (pre-resolved)
                if anchor_scene_id:
                    vid = anchor_scene_map.get(anchor_scene_id)
                    if vid is not None:
                        anchor_vid = vid
                break

        if is_anchor and anchor_vid and anchor_vid in video_info:
            vid = anchor_vid
            # Szene finden und deren Start nutzen
            scene_info = None
            if anchor_scene_id:
                for s in video_info[vid].get("scenes", []):
                    if str(s["id"]) == str(anchor_scene_id):
                        scene_info = s
                        break
            source_start = scene_info["start"] if scene_info else 0.0
        else:
            # Normaler Clip-Match
            vid, source_start = _match_video_for_segment(
                seg_start, seg_end, settings.vibe,
                video_info, available_ids, clip_offsets, used_recently,
                energy_per_beat=energy_per_beat, beats=beats,
                memory_bias=memory_bias,
            )

        if vid == -1:
            logger.warning("Kein Video fuer Segment %.2f-%.2f verfuegbar, ueberspringe.", seg_start, seg_end)
            continue

        vid_duration = video_info[vid]["duration"]
        vid_path = video_info[vid]["path"]

        # Intelligent looping: Reset wenn nicht genug Material
        remaining = vid_duration - source_start
        if remaining < seg_duration:
            source_start = 0.0
            clip_offsets[vid] = 0.0

        source_end = min(source_start + seg_duration, vid_duration)

        # PhD-Spec: Bestimme Sektion und Crossfade-Dauer fuer dieses Segment
        seg_section = get_section_at_time(sections, seg_start)
        seg_section_type = seg_section.section_type if seg_section else "TRANSITION"
        seg_crossfade = section_to_crossfade(seg_section_type)

        # Bei Drops: Hard Cut erzwingen (0ms crossfade)
        is_drop = any(abs(seg_start - dt) < 0.5 for dt in drop_times)
        if is_drop:
            seg_crossfade = 0.0

        # DJ-Mix Transition: Laengerer Crossfade + "transition" Source-Tag
        is_in_transition = any(
            t_start <= seg_start < t_end for t_start, t_end in transition_ranges
        )
        if is_in_transition and not is_drop:
            seg_crossfade = max(seg_crossfade, 2.0)  # Mindestens 2s Crossfade bei DJ-Uebergang

        segments.append(TimelineSegment(
            video_id=vid,
            video_path=vid_path,
            start=round(seg_start, 4),
            end=round(seg_end, 4),
            source_start=round(source_start, 4),
            source_end=round(source_end, 4),
            is_anchor=is_anchor,
            scene_id=anchor_scene_id,
            crossfade_duration=round(seg_crossfade, 2),
            section_type=seg_section_type,
        ))

        # CutPoint fuer UI-Visualisierung
        if is_in_transition:
            source_type = "transition"
        elif is_drop:
            source_type = "drop"
        elif is_anchor:
            source_type = "anchor"
        else:
            source_type = "beat"
        # Energie-basierte Staerke
        beat_idx = np.searchsorted(beats_arr, seg_start)
        beat_idx = min(beat_idx, len(energy_per_beat) - 1) if energy_per_beat else 0
        strength = energy_per_beat[beat_idx] if beat_idx < len(energy_per_beat) else 0.5
        cut_points.append(CutPoint(
            time=round(seg_start, 4),
            source=source_type,
            strength=round(min(1.0, strength + 0.2), 3),
        ))

        # Offsets aktualisieren (F-018: gecappte source_end nutzen)
        clip_offsets[vid] = source_end
        if clip_offsets[vid] >= vid_duration:
            clip_offsets[vid] = 0.0

        # F-019: Begrenze used_recently auf 10 Eintraege (nur letzte 3 werden gelesen)
        used_recently.append(vid)
        if len(used_recently) > 10:
            used_recently[:] = used_recently[-10:]

    if progress_cb:
        progress_cb(100, "Timeline fertig")
    logger.info(
        "Phase 3: %d Segmente, %d CutPoints, %.1fs Gesamtdauer",
        len(segments), len(cut_points), total_duration,
    )
    return segments, cut_points


# ======================================================================
# Phase 3: Keyframe-String Generator
# ======================================================================

def _motion_category(score: float) -> str:
    """Ordnet einen RAFT-Motion-Score einer lesbaren Kategorie zu."""
    if score >= 0.8:
        return "Extrem"
    elif score >= 0.6:
        return "Action"
    elif score >= 0.3:
        return "Moderat"
    else:
        return "Ruhig"


def generate_keyframe_string(video_id: int) -> str:
    """Wandelt erkannte Video-Szenen und RAFT-Motion-Werte in einen lesbaren Text-String um.

    Format:
        [Szene 1: Ruhig (motion=0.12), Laenge: 10.3s]
          -> [Szene 2: Action (motion=0.85), Laenge: 4.1s]
    """
    with Session(engine) as session:
        clip = session.get(VideoClip, video_id)
        if not clip:
            return f"[Video {video_id}: nicht gefunden]"

        scenes = sorted(clip.scenes, key=lambda s: s.start_time)
        if not scenes:
            dur = clip.duration or 0.0
            return f"[Video '{Path(clip.file_path).stem}': Keine Szenen erkannt, Laenge: {dur:.1f}s]"

        res = f"{clip.width or '?'}x{clip.height or '?'}" if clip.width else "?"

        parts = []
        for i, scene in enumerate(scenes):
            motion = scene.energy or 0.0  # motion_score als energy gespeichert
            cat = _motion_category(motion)
            length = (scene.end_time or 0.0) - (scene.start_time or 0.0)
            part = f"[Szene {i+1}: {cat} (motion={motion:.2f}), Laenge: {length:.1f}s, {res}]"
            parts.append(part)

        video_name = Path(clip.file_path).stem
        header = f"Video: '{video_name}' ({len(scenes)} Szenen)\n"
        return header + "\n  -> ".join(parts)


def generate_keyframe_strings_for_project(project_id: int = 1) -> str:
    """Generiert Keyframe-Strings fuer ALLE Video-Clips eines Projekts.

    M10 Fix: Laedt alle Clips mit ihren Scenes in einer einzigen Session
    statt N+1 separate Sessions (1 fuer Clip-IDs + N fuer Videos).
    """
    from sqlalchemy.orm import joinedload

    with Session(engine) as session:
        clips = (
            session.query(VideoClip)
            .options(joinedload(VideoClip.scenes))
            .filter_by(project_id=project_id)
            .all()
        )
        if not clips:
            return "[Keine Video-Clips im Projekt]"

        all_strings = []
        for clip in clips:
            scenes = sorted(clip.scenes, key=lambda s: s.start_time)
            if not scenes:
                dur = clip.duration or 0.0
                all_strings.append(
                    f"[Video '{Path(clip.file_path).stem}': Keine Szenen erkannt, Laenge: {dur:.1f}s]"
                )
                continue

            res = f"{clip.width or '?'}x{clip.height or '?'}" if clip.width else "?"
            parts = []
            for i, scene in enumerate(scenes):
                motion = scene.energy or 0.0
                cat = _motion_category(motion)
                length = (scene.end_time or 0.0) - (scene.start_time or 0.0)
                part = f"[Szene {i+1}: {cat} (motion={motion:.2f}), Laenge: {length:.1f}s, {res}]"
                parts.append(part)

            video_name = Path(clip.file_path).stem
            header = f"Video: '{video_name}' ({len(scenes)} Szenen)\n"
            all_strings.append(header + "\n  -> ".join(parts))

    return "\n\n".join(all_strings)


# ======================================================================
# Phase 3: Dynamisches Motion-Pacing
# ======================================================================


def _match_video_by_motion(
    energy_value: float,
    video_info: dict[int, dict],
    available_ids: list[int],
    used_recently: list[int],
) -> tuple[int, float]:
    """Waehlt den Video-Clip basierend auf Motion-Score passend zur Audio-Energie.

    Ruhige Szenen (motion < 0.3) fuer ruhige Audio-Abschnitte.
    Action-Szenen (motion > 0.7) fuer energetische Audio-Abschnitte.
    """
    if not available_ids:
        logger.warning("_match_video_by_motion: Keine Videos verfuegbar")
        return -1, 0.0

    candidates = [v for v in available_ids if v not in used_recently[-3:]]
    if not candidates:
        candidates = available_ids

    best_vid = candidates[0]
    best_score = -1.0
    best_source_start = 0.0

    for vid in candidates:
        scenes = video_info.get(vid, {}).get("scenes", [])
        if not scenes:
            continue

        for scene in scenes:
            motion = scene.get("energy", 0.5)
            # Score: Je naeher motion an energy_value, desto besser
            match_score = 1.0 - abs(motion - energy_value)
            if match_score > best_score:
                best_score = match_score
                best_vid = vid
                best_source_start = scene.get("start", 0.0)

    return best_vid, best_source_start


# ── KI-Langzeitgedaechtnis ──

def learn_from_anchor(
    audio_track_id: int,
    anchor_time: float,
    scene_id: int | None = None,
    label: str = "",
) -> bool:
    """Speichert eine manuelle Schnitt-Entscheidung als KI-Lern-Beispiel.

    Liest den Audio-Kontext (BPM, Energie) zum Zeitpunkt des Ankers und
    die Video-Entscheidung (RAFT-Motion der Szene) und persistiert beides
    in AIPacingMemory fuer zukuenftige Auto-Edits.

    Args:
        audio_track_id: ID des AudioTrack-Objekts
        anchor_time:    Zeitstempel im Audio (Sekunden)
        scene_id:       Optionale Scene.id fuer Clip-Kontext
        label:          Beschreibung der Regel

    Returns:
        True bei Erfolg, False bei Fehler
    """
    import datetime

    try:
        with Session(engine) as session:
            # DB-10 Fix: Prüfe ob referenzierte Objekte noch existieren
            audio = session.get(AudioTrack, audio_track_id)
            if audio is None:
                logger.warning(
                    "learn_from_anchor: AudioTrack %d existiert nicht mehr, überspringe.",
                    audio_track_id,
                )
                return False
            if scene_id is not None and session.get(Scene, scene_id) is None:
                logger.warning(
                    "learn_from_anchor: Scene %d existiert nicht mehr, überspringe.",
                    scene_id,
                )
                return False

            # ── Audio-Kontext laden ──
            bpm = audio.bpm if audio else None

            overall_energy = None
            beatgrid = session.query(Beatgrid).filter_by(
                audio_track_id=audio_track_id
            ).first()
            if beatgrid and beatgrid.energy_per_beat and beatgrid.beat_positions:
                energy_data = json.loads(beatgrid.energy_per_beat)
                beats_pos = json.loads(beatgrid.beat_positions)
                if beats_pos:
                    beats_arr = np.array(beats_pos)
                    idx = int(np.argmin(np.abs(beats_arr - anchor_time)))
                    if 0 <= idx < len(energy_data):
                        overall_energy = float(energy_data[idx])

            # Stimmung aus Energie ableiten
            if overall_energy is not None:
                if overall_energy > 0.75:
                    mood = "drop"
                elif overall_energy > 0.55:
                    mood = "peak"
                elif overall_energy > 0.35:
                    mood = "buildup"
                elif overall_energy > 0.2:
                    mood = "breakdown"
                else:
                    mood = "warmup"
            else:
                mood = None

            # ── Video/Szenen-Kontext laden ──
            raft_motion = None
            if scene_id:
                scene = session.get(Scene, scene_id)
                if scene:
                    raft_motion = scene.energy  # Scene.energy = RAFT motion score

            # Cut-Typ aus Kontext ableiten
            is_energetic = (overall_energy or 0.5) > 0.65 or (raft_motion or 0.5) > 0.65
            cut_type = "hard_cut" if is_energetic else "crossfade"
            crossfade = 0.0 if cut_type == "hard_cut" else 1.5

            _MOOD_TO_SECTION = {"drop": "DROP", "peak": "DROP", "buildup": "BUILDUP", "breakdown": "BREAKDOWN", "warmup": "WARMUP"}
            section_type = _MOOD_TO_SECTION.get(mood, mood.upper() if mood else None)

            mem = AIPacingMemory(
                created_at=datetime.datetime.now().isoformat(),
                bpm=bpm,
                overall_energy=overall_energy,
                mood=mood,
                audio_time=anchor_time,
                raft_motion=raft_motion,
                cut_type=cut_type,
                crossfade_duration=crossfade,
                section_type=section_type,
                scene_id=scene_id,
                audio_track_id=audio_track_id,
                label=label or f"Anker@{anchor_time:.1f}s",
            )
            session.add(mem)
            session.commit()
            logger.info(
                "AI Memory: Regel gespeichert id=%d bpm=%.1f mood=%s motion=%.2f",
                mem.id, bpm or 0.0, mood or "?", raft_motion or 0.0,
            )
            return True
    except Exception as exc:
        logger.error("learn_from_anchor fehlgeschlagen: %s", exc)
        return False


def record_rl_feedback(audio_track_id: int, sentiment: str, project_id: int = 1) -> bool:
    """Speichert RL-Feedback (thumbs up/down) als AIPacingMemory Eintrag."""
    from datetime import datetime
    try:
        with Session(engine) as session:
            track = session.get(AudioTrack, audio_track_id)
            entry_count = session.query(TimelineEntry).filter_by(
                project_id=project_id, track="video"
            ).count()

            mem = AIPacingMemory(
                created_at=datetime.now().isoformat(),
                audio_track_id=audio_track_id,
                bpm=track.bpm if track else None,
                label=f"rl_feedback_{sentiment}",
                mood=sentiment,
                cut_type=f"feedback_{entry_count}_clips",
            )
            session.add(mem)
            session.commit()
            logger.info("RL-Feedback gespeichert: %s, audio=%d, clips=%d",
                        sentiment, audio_track_id, entry_count)
            return True
    except Exception as exc:
        logger.error("record_rl_feedback fehlgeschlagen: %s", exc)
        return False


def _get_ai_memory_bias(bpm: float, overall_energy: float) -> dict | None:
    """Sucht aehnliche Audio-Situationen im KI-Gedaechtnis.

    Vergleicht BPM und Energie mit gespeicherten Lern-Beispielen.
    Gibt ein Bias-Dict zurueck das auto_edit_phase3 beeinflusst,
    oder None wenn kein aehnliches Beispiel gefunden wurde.

    Schwellwert: BPM-Abweichung < 15% UND Energie-Abweichung < 25%.
    """
    try:
        with Session(engine) as session:
            memories = session.query(AIPacingMemory).filter(
                AIPacingMemory.bpm.between(bpm * 0.85, bpm * 1.15),
                AIPacingMemory.overall_energy.between(overall_energy - 0.25, overall_energy + 0.25)
            ).all()
            if not memories:
                return None

            best_score = 999.0
            best_mem = None

            for mem in memories:
                if mem.bpm is None:
                    continue
                bpm_sim = abs(mem.bpm - bpm) / max(bpm, 1.0)
                energy_sim = abs((mem.overall_energy or 0.5) - overall_energy)
                score = bpm_sim + energy_sim
                if score < best_score:
                    best_score = score
                    best_mem = mem

            # Schwellwert: zu unaehnlich → kein Einfluss
            if best_mem is None or best_score > 0.5:
                return None

            logger.info(
                "AI Memory Bias aktiv: score=%.3f bpm=%.1f->%.1f mood=%s label='%s'",
                best_score, bpm, best_mem.bpm or 0.0,
                best_mem.mood or "?", best_mem.label or "",
            )
            return {
                "preferred_motion": best_mem.raft_motion,
                "preferred_cut_type": best_mem.cut_type,
                "preferred_crossfade": best_mem.crossfade_duration,
                "mood": best_mem.mood,
                "label": best_mem.label,
                "similarity_score": best_score,
            }
    except Exception as exc:
        logger.warning("AI Memory Abfrage fehlgeschlagen: %s", exc)
        return None


# ── Legacy wrapper (backward compat) ──

def auto_edit_to_beats(
    audio_id: int,
    video_clip_ids: list[int],
    total_duration: float = 60.0,
    pacing_curve: list[float] | None = None,
    tempo: int = 50,
) -> list[dict]:
    """Legacy Phase 2 wrapper — delegiert an Phase 3 Engine."""
    # Map tempo slider to base_cut_rate
    if tempo >= 80:
        rate = 1
    elif tempo >= 60:
        rate = 2
    elif tempo >= 40:
        rate = 4
    elif tempo >= 20:
        rate = 8
    else:
        rate = 16

    settings = AdvancedPacingSettings(
        base_cut_rate=rate,
        energy_reactivity=50,
        breakdown_behavior="halve",
        manual_density_curve=pacing_curve,
    )
    segments, _ = auto_edit_phase3(audio_id, video_clip_ids, settings)

    result = []
    for seg in segments:
        if seg.start >= total_duration:
            break
        end = min(seg.end, total_duration)
        result.append({
            "video_id": seg.video_id,
            "start": seg.start,
            "end": end,
            "source_start": seg.source_start,
        })
    return result
