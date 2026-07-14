"""Pacing Beat-Grid Module — Datentypen, Datenzugriff und Section-Detection.

Enthält:
- Gemeinsame Datentypen (PacingSettings, CutPoint, AdvancedPacingSettings, TimelineSegment)
- Beat-Grid Konstanten und Konfiguration
- DB-Datenzugriff (AudioTrack, Beatgrid, VideoClip)
- Stem-Audio-Cache
- Stem-gewichtete Energie, Makro-Section-Detection, Drop-Detection
- Vocal-Activity, DJ-Transition-Detektion
"""

import bisect
import collections
import json
import logging
import threading
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
from sqlalchemy import select  # B-624: column-select statt Blob-eager-load
from sqlalchemy.orm import Session, joinedload

from database import engine, AudioTrack, VideoClip
from services.audio_constants import DEFAULT_SR

logger = logging.getLogger(__name__)

# Sentinel value: step so hoch dass kein Cut stattfindet (breakdown_behavior="none")
_STEP_NO_CUT = 9999

# Thread-Lock fuer alle globalen Caches (Race-Condition-Schutz)
_cache_lock = threading.Lock()

# Stem-Audio Cache — LRU-Limit auf 2 audio_ids.
# B-164: Bei 60-min DJ-Mix bei 22050 Hz mono float32 sind 4 Stems ~1.27 GB
# pro audio_id. 5 cached audio_ids = ~6.35 GB RAM (OOM-Risiko bei
# parallelem Demucs/SigLIP). 2 reicht fuer den typischen Workflow
# "auto-edit fuer EINEN Mix mit gelegentlichem Re-Run".
_STEM_CACHE_MAX = 2
_stem_audio_cache: collections.OrderedDict[int, dict[str, tuple]] = collections.OrderedDict()


def _get_cached_stem_audio(audio_id: int, stem_path: str, stem_name: str, sr: int = 22050):
    """Laedt Stem-Audio mit LRU-Cache — vermeidet 4x librosa.load pro auto_edit.

    Limit: max _STEM_CACHE_MAX audio_ids im Cache (~30MB pro Stem × 4 = ~120MB pro Track).
    Bei Ueberschreitung wird der aelteste Eintrag entfernt.
    """
    with _cache_lock:
        if audio_id not in _stem_audio_cache:
            _stem_audio_cache[audio_id] = {}
            # LRU-Eviction: aeltesten Eintrag entfernen wenn Limit erreicht
            evicted_items = []
            while len(_stem_audio_cache) > _STEM_CACHE_MAX:
                evicted_id, evicted_data = _stem_audio_cache.popitem(last=False)
                evicted_items.append((evicted_id, evicted_data))
                logger.debug("[StemCache] Evicted audio_id=%d", evicted_id)
        else:
            evicted_items = []
            # Move to end (most recently used)
            _stem_audio_cache.move_to_end(audio_id)
        cache = _stem_audio_cache[audio_id]
        if stem_name in cache:
            return cache[stem_name]

    # GC outside lock to avoid holding it during collection
    for _evicted_id, evicted_data in evicted_items:
        for _y_ref, _sr_ref in evicted_data.values():
            del _y_ref
        del evicted_data
    if evicted_items:
        import gc as _gc
        _gc.collect()

    # librosa.load AUSSERHALB des Locks (CPU-intensiv, soll nicht blockieren)
    import librosa
    y, loaded_sr = librosa.load(stem_path, sr=sr, mono=True)

    with _cache_lock:
        if audio_id not in _stem_audio_cache:
            _stem_audio_cache[audio_id] = {}
        _stem_audio_cache[audio_id][stem_name] = (y, loaded_sr)
    return (y, loaded_sr)


def invalidate_pacing_caches():
    """Cache leeren nach Media-Import oder DB-Änderung."""
    _get_audio_duration.cache_clear()
    _get_audio_path.cache_clear()
    _get_bpm.cache_clear()
    _get_video_info_cached.cache_clear()
    with _cache_lock:
        _stem_audio_cache.clear()


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
    high_energy_behavior: str = "none"  # "none", "force1", "peak-time"
    vibe: str = ""                  # Keyword fuer Semantic Search
    manual_density_curve: list[float] | None = None
    anchors: list[dict] | None = None  # [{"time": float, "scene_id": str}, ...]
    use_llm_strategist: bool = False   # Phase 5: Lokaler LLM-Pacing-Strategist
    use_llm_pacing: bool = False       # Hybrid-Pipeline: Direktes Ollama EDL-Reasoning
    user_preferences: str = ""         # Natuerliche Sprache fuer LLM ("ruhigere Breakdowns")
    transition_type: str = "cut"  # "cut" (hart, Standard) oder "crossfade" (experimentell, B9)


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
    degraded: bool = False


SECTION_PACING_MAP = {
    "WARMUP":     {"base": 16, "min": 8,  "max": 32},
    "BUILDUP":    {"base": 8,  "min": 1,  "max": 16},
    "DROP":       {"base": 2,  "min": 1,  "max": 4},
    "BREAKDOWN":  {"base": 16, "min": 8,  "max": 32},
    "TRANSITION": {"base": 8,  "min": 4,  "max": 16},
    "COOLDOWN":   {"base": 16, "min": 8,  "max": 32},
    "CHORUS":     {"base": 4,  "min": 2,  "max": 8},
    "VERSE":      {"base": 8,  "min": 4,  "max": 16},
}

HARD_MIN_DURATION = 3.0
SECTION_MIN_DURATION = {
    "WARMUP": 5.0, "BUILDUP": 3.0, "DROP": 2.0,
    "BREAKDOWN": 6.0, "TRANSITION": 4.0, "COOLDOWN": 6.0,
    "CHORUS": 3.0, "VERSE": 4.0,
}


# ── Data Access ──

def _get_beat_positions(audio_id: int | None) -> list[float]:
    """Laedt die exakten Beat-Positionen aus dem Beatgrid der DB.

    Fallback: Wenn kein Beatgrid vorhanden ist, wird ein synthetisches Grid
    aus track.bpm generiert. Das reduziert die Pacing-Qualitaet (keine Downbeats,
    keine energy_per_beat). BeatAnalysisService sollte vorher gelaufen sein.

    Hinweis: track.bpm und beatgrid.bpm koennen divergieren wenn track.bpm
    manuell editiert oder von einem anderen Service ueberschrieben wurde.
    """
    if audio_id is None:
        return []
    with Session(engine) as session:
        track = session.query(AudioTrack).filter(
            AudioTrack.id == audio_id, AudioTrack.deleted_at.is_(None)
        ).options(joinedload(AudioTrack.beatgrid)).first()
        if not track or not track.beatgrid:
            return []
        bg = track.beatgrid
        if bg.beat_positions:
            try:
                # H7-FIX: Column(JSON) deserialisiert automatisch.
                # Backward-compat: isinstance-Check fuer alte doppelt-serialisierte Daten.
                positions = json.loads(bg.beat_positions) if isinstance(bg.beat_positions, str) else bg.beat_positions
                return [float(p) for p in positions]
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("Parsing beat_positions JSON for audio_id=%s: %s", audio_id, e)
        if bg.bpm and bg.bpm > 0:
            interval = 60.0 / bg.bpm
            # FIX-2.2: Guard gegen Endlosschleife bei extrem kleinem BPM
            if interval < 0.01:
                logger.warning("BPM %.1f ergibt interval=%.4fs — ueberspringe Fallback-Beats", bg.bpm, interval)
                return []
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
) -> tuple[list[float], list[float], list[float], bool]:
    """Laedt beat_positions, downbeat_positions und energy_per_beat in EINER Session.

    Bug-14 Fix: Kombiniert die drei separaten DB-Sessions (_get_beat_positions,
    _get_downbeat_positions, _get_energy_per_beat) in einen einzigen Round-Trip.
    Vorher: 3 Sessions für die gleiche AudioTrack/Beatgrid-Zeile.

    Returns: (beat_positions, downbeat_positions, energy_per_beat, is_fallback)
    """
    if audio_id is None:
        return [], [], [], False
    with Session(engine) as session:
        track = session.query(AudioTrack).filter(
            AudioTrack.id == audio_id, AudioTrack.deleted_at.is_(None)
        ).options(joinedload(AudioTrack.beatgrid)).first()
        if not track or not track.beatgrid:
            return [], [], [], False
        bg = track.beatgrid

        # beat_positions (mit BPM-Fallback)
        beat_positions: list[float] = []
        is_fallback = False
        if bg.beat_positions:
            try:
                # H7-FIX: Column(JSON) deserialisiert automatisch — isinstance-Check fuer Backward-compat.
                raw_bp = json.loads(bg.beat_positions) if isinstance(bg.beat_positions, str) else bg.beat_positions
                beat_positions = [float(p) for p in raw_bp]
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("Parsing beat_positions JSON in combined loader for audio_id=%s: %s", audio_id, e)
        if not beat_positions and bg.bpm and bg.bpm > 0:
            is_fallback = True
            interval = 60.0 / bg.bpm
            # BUG-013 Fix: Guard gegen Endlosschleife bei extrem kleinem BPM (identisch zu _get_beat_positions)
            if interval < 0.01:
                logger.warning("BPM %.1f ergibt interval=%.4fs — ueberspringe Fallback-Beats", bg.bpm, interval)
            else:
                duration = track.duration or 300.0
                t = bg.offset or 0.0
                while t < duration:
                    beat_positions.append(round(t, 4))
                    t += interval

        # downbeat_positions
        downbeat_positions: list[float] = []
        if bg.downbeat_positions:
            try:
                # H7-FIX: Column(JSON) deserialisiert automatisch — isinstance-Check fuer Backward-compat.
                raw_dp = json.loads(bg.downbeat_positions) if isinstance(bg.downbeat_positions, str) else bg.downbeat_positions
                downbeat_positions = [float(p) for p in raw_dp]
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("Parsing downbeat_positions JSON for audio_id=%s: %s", audio_id, e)

        # energy_per_beat
        energy_per_beat: list[float] = []
        if bg.energy_per_beat:
            try:
                # H7-FIX: Column(JSON) deserialisiert automatisch — isinstance-Check fuer Backward-compat.
                raw_epb = json.loads(bg.energy_per_beat) if isinstance(bg.energy_per_beat, str) else bg.energy_per_beat
                energy_per_beat = [float(e) for e in raw_epb]
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning("Parsing energy_per_beat JSON for audio_id=%s: %s", audio_id, e)

        return beat_positions, downbeat_positions, energy_per_beat, is_fallback


@lru_cache(maxsize=64)
def _get_audio_duration(audio_id: int) -> float:
    """Gibt die Dauer des Audio-Tracks in Sekunden zurueck."""
    with Session(engine) as session:
        track = session.query(AudioTrack).filter(
            AudioTrack.id == audio_id, AudioTrack.deleted_at.is_(None)
        ).first()
        return track.duration if track and track.duration else 60.0


@lru_cache(maxsize=64)
def _get_audio_path(audio_id: int) -> str:
    """Gibt den Dateipfad des Audio-Tracks zurueck."""
    with Session(engine) as session:
        track = session.query(AudioTrack).filter(
            AudioTrack.id == audio_id, AudioTrack.deleted_at.is_(None)
        ).first()
        return track.file_path if track else ""


def _engine_cache_identity() -> tuple[int, str]:
    return id(engine), str(getattr(engine, "url", ""))


@lru_cache(maxsize=64)
def _get_bpm_cached(engine_identity: tuple[int, str], audio_id: int) -> float | None:
    # engine_identity is part of the cache key; Session still uses current module engine.
    if audio_id is None:
        return None
    with Session(engine) as session:
        # B-624: nur Skalar-Spalte bpm laden statt ORM-Objekt mit Blob-Spalten
        row = session.execute(
            select(AudioTrack.bpm).where(
                AudioTrack.id == audio_id, AudioTrack.deleted_at.is_(None)
            )
        ).first()
        return row.bpm if row else None


def _get_bpm(audio_id: int | None) -> float | None:
    if audio_id is None:
        return None
    return _get_bpm_cached(_engine_cache_identity(), int(audio_id))


_get_bpm.cache_clear = _get_bpm_cached.cache_clear
_get_bpm.cache_info = _get_bpm_cached.cache_info


def _get_video_info(video_ids: list[int]) -> dict[int, dict]:
    """Holt Video-Metadaten (Dauer, Pfad) fuer alle IDs. Cached intern."""
    import copy
    return copy.deepcopy(_get_video_info_cached(tuple(sorted(video_ids))))


@lru_cache(maxsize=32)
def _get_video_info_cached(video_ids: tuple[int, ...]) -> dict[int, dict]:
    """Cached-Backend fuer _get_video_info (tuple ist hashable).

    Nutzt joinedload um N+1 Lazy-Loading zu vermeiden — ohne joinedload
    wuerden 50 Clips = 50 separate Scene-Queries, die den Connection Pool
    erschoepfen koennen (QueuePool limit reached).
    """
    info = {}
    if not video_ids:
        return info
    with Session(engine) as session:
        clips = (
            session.query(VideoClip)
            .options(joinedload(VideoClip.scenes))
            .filter(VideoClip.id.in_(video_ids), VideoClip.deleted_at.is_(None))
            .all()
        )
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
        clip = session.query(VideoClip).filter(
            VideoClip.id == video_id, VideoClip.deleted_at.is_(None)
        ).options(joinedload(VideoClip.scenes)).first()
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

    ACHTUNG: Liest alle 4 Stem-Files von Disk bei jedem Aufruf (librosa.load).
    Bei 60min DJ-Mix = 4x librosa.load. Nicht gecacht — wird bei jedem auto_edit_phase3() neu berechnet.

    PhD-Spec Abschnitt 3.3:
      E_weighted(t) = w_drums * E_drums(t) + w_bass * E_bass(t)
                    + w_vocals * E_vocals(t) + w_other * E_other(t)

    Faellt auf die Stereo-Summe zurueck wenn Stems nicht vorhanden sind.
    """
    with Session(engine) as session:
        track = session.query(AudioTrack).filter(
            AudioTrack.id == audio_id, AudioTrack.deleted_at.is_(None)
        ).first()
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

    def _compute_rms_per_beat(stem_name: str, audio_path: str, beats_list: list[float]) -> list[float]:
        """Berechnet RMS pro Beat-Intervall fuer eine einzelne Stem-Datei.

        P-027 Fix: Nutzt _get_cached_stem_audio statt direktem librosa.load.
        """
        try:
            y, sr = _get_cached_stem_audio(audio_id, audio_path, stem_name, sr=DEFAULT_SR)
        except (OSError, IOError, ValueError, RuntimeError) as e:
            logger.warning("Konnte Stem '%s' nicht laden: %s", audio_path, e)
            return [0.5] * len(beats_list)

        audio_duration = len(y) / sr
        energies = []
        for i in range(len(beats_list)):
            start_sec = beats_list[i]
            end_sec = beats_list[i + 1] if i + 1 < len(beats_list) else audio_duration
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
            stem_energies[stem_name] = _compute_rms_per_beat(stem_name, available[stem_name], beats)
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
    # P-020 Fix: O(N*M) -> O(N*log(M)) via bisect statt sum(1 for b in beats ...)
    beats_arr_sorted = sorted(beats)  # should already be sorted
    merged: list[Section] = []
    for sec in sections:
        sec_beats = 0
        if beats_arr_sorted:
            left = bisect.bisect_left(beats_arr_sorted, sec.start)
            right = bisect.bisect_left(beats_arr_sorted, sec.end)
            sec_beats = right - left

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


# P-021: Bisect-Cache fuer get_section_at_time (O(log N) statt O(N), aufgerufen 5451x)
# B-160: Cache-Key NICHT id(sections) (id-Reuse nach GC liefert Stale-Cache),
# sondern stabiler Tuple-Hash der Sektions-Inhalte.
_section_starts_cache: list[float] = []
_section_list_cache: list[Section] = []
_section_cache_signature: tuple | None = None
_section_cache_lock = threading.Lock()


def _sections_signature(sections: list[Section]) -> tuple:
    """B-160: Stable hash for Section-list identity. Tuple of (start, end, type)
    survives GC + memory-address reuse, which a builtin object-id check does not."""
    return tuple((s.start, s.end, s.section_type) for s in sections)


def get_section_at_time(sections: list[Section], time: float) -> Section | None:
    """Findet die Sektion die einen bestimmten Zeitpunkt enthaelt. O(log N) via bisect.

    Thread-safe durch _section_cache_lock (verhindert Race Conditions bei
    parallelen Aufrufen mit unterschiedlichen Section-Listen).

    B-160: Cache-Key ist Tuple-Signature der Sektions-Inhalte, nicht eine
    Adresse. Sonst kollidiert die id() nach GC und der Cache liefert alte Daten.
    """
    global _section_starts_cache, _section_list_cache, _section_cache_signature
    if not sections:
        return None
    sig = _sections_signature(sections)
    with _section_cache_lock:
        # Build cache on first call or when sections content changes
        if _section_cache_signature != sig:
            _section_starts_cache = [s.start for s in sections]
            _section_list_cache = list(sections)
            _section_cache_signature = sig
        idx = bisect.bisect_right(_section_starts_cache, time) - 1
        if 0 <= idx < len(_section_list_cache):
            sec = _section_list_cache[idx]
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
        track = session.query(AudioTrack).filter(
            AudioTrack.id == audio_id, AudioTrack.deleted_at.is_(None)
        ).first()
        if not track or not track.stem_vocals_path:
            return [False] * len(beats)
        vocals_path = track.stem_vocals_path

    if not Path(vocals_path).exists():
        return [False] * len(beats)

    if not beats or len(beats) < 2:
        return [False] * len(beats)

    try:
        # P-028 Fix: Nutze _get_cached_stem_audio statt direktem librosa.load
        y, sr = _get_cached_stem_audio(audio_id, vocals_path, "vocals", sr=DEFAULT_SR)
    except (OSError, IOError, ValueError, RuntimeError) as e:
        logger.warning("Konnte Vocal-Stem '%s' nicht laden: %s", vocals_path, e)
        return [False] * len(beats)

    audio_duration = len(y) / sr
    activity = []
    for i in range(len(beats)):
        start_sec = beats[i]
        end_sec = beats[i + 1] if i + 1 < len(beats) else audio_duration
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
            confidence = min(1.0, (curr - prev_avg) / max(post_threshold, 0.01))
            if i < len(beats):
                drops.append(DropEvent(
                    time=beats[i],
                    confidence=round(confidence, 3),
                    energy_before=round(prev_avg, 3),
                    energy_after=round(curr, 3),
                ))

    logger.info("Drop-Detection: %d Drops erkannt", len(drops))
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

    # Normalisiere (biased Varianz-Schaetzer — fuer relative Erkennung ausreichend)
    _max_v = float(np.max(variance))
    max_var = _max_v if _max_v > 0 else 1.0
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


# ======================================================================
# F-010: Stem-Quality-Metriken (SNR per Stem)
# F-011: Drum-Onset-Detection auf isoliertem Drums-Stem
# ======================================================================

@dataclass
class StemSNR:
    """SNR-Metriken (Signal-to-Noise Ratio in dB) fuer jeden Demucs-Stem.

    Hoeherer Wert = sauberere Separation. Richtwerte:
      > 20 dB: Exzellent (kaum Bleed-Through)
      10-20 dB: Gut (typisch fuer htdemucs_ft)
      < 10 dB: Schwach (viel Bleed-Through vom Originalmix)
    """
    drums: float
    bass: float
    vocals: float
    other: float


def compute_stem_snr(audio_id: int) -> StemSNR | None:
    """F-010: Berechnet SNR-Qualitaetsmetrik fuer jeden Demucs-Stem.

    Methode: SNR = 20 * log10(P90_rms / max(P10_rms, epsilon))
      P90 = 90th Percentile der Frame-RMS → repraesentiert den Signal-Pegel
      P10 = 10th Percentile der Frame-RMS → repraesentiert Rauschen / Bleed-Through

    Nutzt _get_cached_stem_audio um wiederholtes librosa.load zu vermeiden.
    Returns None wenn keine Stems vorhanden sind.
    """
    with Session(engine) as session:
        # B-624: nur Stem-Pfad-Skalarspalten laden statt ORM-Objekt mit Blob-Spalten
        row = session.execute(
            select(
                AudioTrack.stem_drums_path,
                AudioTrack.stem_bass_path,
                AudioTrack.stem_vocals_path,
                AudioTrack.stem_other_path,
            ).where(
                AudioTrack.id == audio_id, AudioTrack.deleted_at.is_(None)
            )
        ).first()
        if not row:
            return None
        stem_paths = {
            "drums": row.stem_drums_path,
            "bass": row.stem_bass_path,
            "vocals": row.stem_vocals_path,
            "other": row.stem_other_path,
        }

    available = {k: v for k, v in stem_paths.items() if v and Path(v).exists()}
    if not available:
        logger.info("Keine Stems fuer SNR-Berechnung (audio_id=%d)", audio_id)
        return None

    try:
        import librosa
    except ImportError:
        logger.warning("librosa nicht verfuegbar fuer SNR-Berechnung")
        return None

    def _snr_for_stem(stem_name: str, path: str) -> float:
        try:
            y, sr = _get_cached_stem_audio(audio_id, path, stem_name, sr=DEFAULT_SR)
        except (OSError, IOError, ValueError, RuntimeError) as e:
            logger.warning("Konnte Stem '%s' nicht laden fuer SNR: %s", path, e)
            return 0.0
        frame_rms = librosa.feature.rms(y=y, frame_length=2048, hop_length=512)[0]
        if len(frame_rms) < 10:
            return 0.0
        p10 = float(np.percentile(frame_rms, 10))
        p90 = float(np.percentile(frame_rms, 90))
        snr_db = 20.0 * np.log10(max(p90, 1e-8) / max(p10, 1e-8))
        return round(float(snr_db), 2)

    snr_values: dict[str, float] = {}
    for stem_name in ["drums", "bass", "vocals", "other"]:
        if stem_name in available:
            snr_values[stem_name] = _snr_for_stem(stem_name, available[stem_name])
        else:
            snr_values[stem_name] = 0.0

    result = StemSNR(
        drums=snr_values["drums"],
        bass=snr_values["bass"],
        vocals=snr_values["vocals"],
        other=snr_values["other"],
    )
    logger.info(
        "Stem-SNR: drums=%.1f dB, bass=%.1f dB, vocals=%.1f dB, other=%.1f dB",
        result.drums, result.bass, result.vocals, result.other,
    )
    return result


def detect_dj_mix_from_stems(audio_id: int, n_segments: int = 5) -> bool:
    """AUD-97: Stem-basierte DJ-Mix-Erkennung auf dem isolierten Drums-Stem.

    Primaer: Drums-Stem (isoliert, kein Bleed-Through von anderen Instrumenten).
    Fallback: Bass-Stem, dann Vocals-Stem wenn Drums nicht verfuegbar.

    Methode:
    - Teilt den Stem in n_segments gleichmaessige Abschnitte
    - Berechnet librosa.beat.beat_track() fuer jeden Abschnitt
    - BPM-Varianz (max - min) > BPM_VARIANCE_THRESHOLD → DJ-Mix erkannt

    Vorteil gegenueber Stereo-BPM-Analyse: Der isolierte Drums-Stem liefert
    praezisere Beat-Tracking-Ergebnisse, weil keine harmonischen Stoersignale
    (Bass, Melodie, Vocals) die Onset-Detection beeinflussen.

    Returns True wenn DJ-Mix erkannt, False sonst.
    """
    with Session(engine) as session:
        track = session.query(AudioTrack).filter(
            AudioTrack.id == audio_id, AudioTrack.deleted_at.is_(None)
        ).first()
        if not track:
            return False
        stem_paths = {
            "drums": track.stem_drums_path,
            "bass":  track.stem_bass_path,
            "vocals": track.stem_vocals_path,
        }

    # Bevorzuge Drums (praeziseste Rhythmus-Information), dann Bass, dann Vocals
    chosen_stem: str | None = None
    chosen_path: str | None = None
    for stem_name in ("drums", "bass", "vocals"):
        p = stem_paths.get(stem_name)
        if p and Path(p).exists():
            chosen_stem = stem_name
            chosen_path = p
            break

    if chosen_path is None:
        logger.debug("detect_dj_mix_from_stems: keine Stems verfuegbar (audio_id=%d)", audio_id)
        return False

    try:
        import librosa
    except ImportError:
        logger.warning("detect_dj_mix_from_stems: librosa nicht verfuegbar")
        return False

    try:
        from services.audio_constants import (
            BPM_VARIANCE_THRESHOLD, MIN_MIX_DURATION_SEC, LIKELY_MIX_DURATION_SEC,
        )

        y, sr = _get_cached_stem_audio(audio_id, chosen_path, chosen_stem, sr=DEFAULT_SR)
        duration = len(y) / sr

        if duration < MIN_MIX_DURATION_SEC:
            logger.debug(
                "detect_dj_mix_from_stems: Stem zu kurz (%.0fs < %.0fs)",
                duration, MIN_MIX_DURATION_SEC,
            )
            return False

        if duration >= LIKELY_MIX_DURATION_SEC:
            logger.info(
                "detect_dj_mix_from_stems: Stem laenger als %.0fs — DJ-Mix angenommen",
                LIKELY_MIX_DURATION_SEC,
            )
            return True

        # Sicherstellen dass Segmente mindestens 10 Sekunden lang sind
        min_seg_sec = 10
        effective_n = min(n_segments, max(2, int(duration / min_seg_sec)))
        seg_samples = int(duration / effective_n * sr)

        tempos: list[float] = []
        for i in range(effective_n):
            start = i * seg_samples
            end = min(start + seg_samples, len(y))
            if (end - start) < sr * 5:  # Mindestens 5s Segment
                continue
            seg = y[start:end]
            t, _ = librosa.beat.beat_track(y=seg, sr=sr)
            tempos.append(float(np.atleast_1d(t)[0]))

        if len(tempos) < 2:
            logger.debug("detect_dj_mix_from_stems: zu wenig Segmente auswertbar")
            return False

        tempo_arr = np.array(tempos)
        tempo_var = float(np.ptp(tempo_arr))  # max - min
        logger.info(
            "detect_dj_mix_from_stems (%s): BPMs=%s Varianz=%.2f BPM_THRESHOLD=%.1f",
            chosen_stem, [round(t, 1) for t in tempos], tempo_var, BPM_VARIANCE_THRESHOLD,
        )

        if tempo_var > BPM_VARIANCE_THRESHOLD:
            logger.info(
                "detect_dj_mix_from_stems: BPM-Varianz %.2f > %.1f — DJ-Mix erkannt via Stems",
                tempo_var, BPM_VARIANCE_THRESHOLD,
            )
            return True

        return False

    except (OSError, IOError, ValueError, RuntimeError):
        logger.exception("detect_dj_mix_from_stems fehlgeschlagen (audio_id=%d)", audio_id)
        return False


@dataclass
class DrumOnset:
    """Ein erkannter Drum-Onset (Kick, Snare, Clap) im isolierten Drums-Stem."""
    time: float      # Onset-Zeitpunkt in Sekunden
    strength: float  # Relative Staerke (0.0-1.0, normalisiert auf Track-Maximum)


def compute_drum_onsets(
    audio_id: int,
    min_strength: float = 0.3,
    max_onsets: int = 2000,
) -> list[DrumOnset]:
    """F-011: Praezise Drum-Onset-Detection auf dem isolierten Drums-Stem.

    Nutzt librosa.onset.onset_detect auf dem Drums-Stem fuer sub-Beat-genaue
    Erkennung von Kicks, Snares und Claps. Liefert praezisere Cut-Punkte
    als das BPM-Grid allein — besonders wichtig in DROP-Sektionen.

    Parameter:
      min_strength: Onset-Staerke-Schwelle (0.0-1.0). Schwache Onsets werden
                    ignoriert. Default 0.3 filtert Ghost-Notes heraus.
      max_onsets:   Maximale Anzahl beibehaltener Onsets (nach Staerke sortiert).
                    Begrenzt RAM-Verbrauch bei sehr langen DJ-Mixes.

    Faellt auf leere Liste zurueck wenn kein Drums-Stem vorhanden.
    Returns: Zeitlich sortierte Liste von DrumOnset-Objekten.
    """
    with Session(engine) as session:
        track = session.query(AudioTrack).filter(
            AudioTrack.id == audio_id, AudioTrack.deleted_at.is_(None)
        ).first()
        if not track or not track.stem_drums_path:
            return []
        drums_path = track.stem_drums_path

    if not Path(drums_path).exists():
        return []

    try:
        import librosa
    except ImportError:
        logger.warning("librosa nicht verfuegbar fuer Drum-Onset-Detection")
        return []

    try:
        y, sr = _get_cached_stem_audio(audio_id, drums_path, "drums", sr=DEFAULT_SR)
    except (OSError, IOError, ValueError, RuntimeError) as e:
        logger.warning("Konnte Drums-Stem '%s' nicht laden: %s", drums_path, e)
        return []

    # Onset-Staerke-Funktion (kombiniert Flux + RMS — ideal fuer perkussive Signale)
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=512)

    # Onset-Frames bestimmen (backtrack=True snappe auf echten Peak-Frame)
    onset_frames = librosa.onset.onset_detect(
        onset_envelope=onset_env,
        sr=sr,
        hop_length=512,
        backtrack=True,
        units='frames',
    )

    if len(onset_frames) == 0:
        return []

    onset_times = librosa.frames_to_time(onset_frames, sr=sr, hop_length=512)

    max_strength = float(np.max(onset_env))
    if max_strength <= 0:
        return []

    onsets: list[DrumOnset] = []
    for frame, time in zip(onset_frames, onset_times):
        strength = float(onset_env[frame]) / max_strength if frame < len(onset_env) else 0.5
        if strength >= min_strength:
            onsets.append(DrumOnset(
                time=round(float(time), 4),
                strength=round(strength, 4),
            ))

    # Bei sehr langen Mixes: behalte nur die staerksten max_onsets
    if len(onsets) > max_onsets:
        onsets.sort(key=lambda o: o.strength, reverse=True)
        onsets = onsets[:max_onsets]
        onsets.sort(key=lambda o: o.time)

    logger.info(
        "Drum-Onsets erkannt: %d Onsets (min_strength=%.2f) auf Drums-Stem",
        len(onsets), min_strength,
    )
    return onsets


def refine_cut_points_with_onsets(
    audio_id: int,
    cut_times: list[float],
    window_sec: float = 0.08,
    min_onset_strength: float = 0.4,
) -> list[float]:
    """AUD-83: Snappe Cut-Zeitpunkte auf gespeicherte Kick/Snare-Onsets.

    Lädt die Onset-Daten aus der DB (vorher von OnsetRhythmService gespeichert)
    und snapped jeden Cut auf den nächsten starken Onset innerhalb window_sec.
    Cuts ohne nahen Onset bleiben unverändert.

    Args:
        audio_id: AudioTrack.id
        cut_times: Beat-aligned Schnittpunkte
        window_sec: Maximales Snap-Fenster (Standard 80ms)
        min_onset_strength: Minimale Onset-Stärke für Snapping

    Returns:
        Verfeinerte Schnittpunkte (zeitlich sortiert, ohne Duplikate)
    """
    try:
        from services.onset_rhythm_service import OnsetRhythmService
        svc = OnsetRhythmService()
        analysis = svc.load_from_db(audio_id)
        if analysis is None:
            return list(cut_times)
        return svc.refine_cut_points(cut_times, analysis, window_sec, min_onset_strength)
    except (ImportError, ValueError, RuntimeError, OSError) as e:
        logger.warning("refine_cut_points_with_onsets: Fehler — %s", e)
        return list(cut_times)
