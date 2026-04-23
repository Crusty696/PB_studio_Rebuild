"""Pacing Edit Helpers — Kandidaten-Auswahl, Clip-Scoring und Keyframe-Generierung.

Enthält:
- Fortgeschrittene Cut-Beat-Auswahl (_compute_effective_step, _select_cut_beats_advanced)
- Mindestdauer-Erzwingung (_enforce_minimum_durations)
- Multi-dimensionales Clip-Fitness-Scoring (_precompute_mood_embeddings, _compute_clip_fitness)
- Cross-Modal Audio-zu-Video Matching (CrossModalMatcher)
- Clip-Matching (_match_video_for_segment, _match_video_by_motion)
- Keyframe-String-Generator (generate_keyframe_string, generate_keyframe_strings_for_project)

Hinweis: calculate_cut_points / calculate_drum_cuts leben in pacing_service.py
um Test-Mocking via patch.object(svc, ...) zu unterstuetzen.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sqlalchemy.orm import Session, joinedload

from database import engine, VideoClip
from services.pacing_beat_grid import (
    _STEP_NO_CUT,
    SECTION_PACING_MAP,
    HARD_MIN_DURATION,
    SECTION_MIN_DURATION,
    get_section_at_time,
    AdvancedPacingSettings,
)

logger = logging.getLogger(__name__)


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
    section_type: str = "",
    section_progress: float = 0.0,
    pacing_map: dict | None = None,
    high_energy_behavior: str = "none",
) -> int:
    """Berechnet den effektiven Beat-Schritt fuer einen bestimmten Beat.

    Kombiniert:
    - base_cut_rate (aus UI)
    - section_type / section_progress (SECTION_PACING_MAP, Phase 1+4)
    - energy_reactivity (erhoeht Cuts bei hohem RMS)
    - breakdown_behavior (reduziert Cuts bei niedrigem RMS)
    - high_energy_behavior (erzwingt Pacing bei hohem RMS)
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
        # Pacing-Kurve hat hoechste Prioritaet — Section-Logik ueberspringen
        section_type = ""

    # 2. Section-Aware Base Step (Phase 1+4: SECTION_PACING_MAP)
    # FIX-2.3: Optionale pacing_map nutzen (LLM Strategist Overrides)
    _active_map = pacing_map if pacing_map is not None else SECTION_PACING_MAP
    section_step = effective  # Fallback: unmodifizierter base_step / curve_step
    if section_type and section_type in _active_map:
        sec_cfg = _active_map[section_type]
        section_step = sec_cfg["base"]

        # BUILDUP: exponentiell beschleunigen (progress^2.5)
        if section_type == "BUILDUP":
            accel = section_progress ** 2.5
            # progress=0 → base (8), progress=1 → min (1)
            section_step = max(
                sec_cfg["min"],
                int(sec_cfg["base"] - accel * (sec_cfg["base"] - sec_cfg["min"])),
            )

        # DROP: erste 8 Beats Step=1, danach auf base einpendeln
        elif section_type == "DROP":
            if section_progress < 0.15:
                section_step = 1
            else:
                section_step = sec_cfg["base"]

    # 3. Energy Reactivity — Energie-Schritt berechnen, dann mit Section blenden
    reactivity = energy_reactivity / 100.0
    energy_step = effective

    # F-007 Fix: Warne bei fehlenden Energy-Daten, nutze 0.5 als Fallback
    if reactivity > 0 and beat_index < len(energy_per_beat):
        energy = energy_per_beat[beat_index]
    else:
        energy = 0.5
        if reactivity > 0:
            logger.warning("F-007: Energy-Fallback 0.5 @ beat %d (reactivity=%.2f, energy_per_beat_len=%d)",
                          beat_index, reactivity, len(energy_per_beat))

    # Hohe Energie (>0.7): Step reduzieren (mehr Cuts)
    if energy > 0.7:
        if high_energy_behavior == "force1":
            energy_step = 1
        elif high_energy_behavior == "force16":
            energy_step = 16
        elif high_energy_behavior == "peak-time":
            # Sehr aggressiv: Step 1 bei sehr hoher Energie, sonst 2
            energy_step = 1 if energy > 0.85 else 2
        else:
            speed_boost = 1.0 + (energy - 0.7) * 3.0 * reactivity  # max ~1.9x
            energy_step = max(1, int(effective / speed_boost))

    # Niedrige Energie (<0.3): Breakdown-Verhalten anwenden
    elif energy < 0.3:
        if breakdown_behavior == "halve":
            energy_step = min(16, effective * 2)
        elif breakdown_behavior == "force16":
            energy_step = 16
        elif breakdown_behavior == "none":
            energy_step = _STEP_NO_CUT

    # Mittlere Energie (0.3-0.7): Leichte Modulation
    elif 0.3 <= energy <= 0.5:
        energy_step = min(16, int(effective * 1.5))

    # Section + Energy blenden: 60% Section, 40% Energy
    if section_type and section_type in SECTION_PACING_MAP:
        sec_cfg = SECTION_PACING_MAP[section_type]
        blended = section_step * 0.6 + energy_step * 0.4
        effective = int(round(blended))
        # Auf Section-Grenzen klemmen
        effective = max(sec_cfg["min"], min(sec_cfg["max"], effective))
    else:
        effective = energy_step

    # Guard: "none" = kein Cut, Motion-Adjustment nicht anwenden
    if effective >= _STEP_NO_CUT:
        return effective

    # 4. Motion-Adjusted Step (PhD-Spec Schritt 3: combined_intensity)
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

    # 5. Vocal-Aware Pacing (PhD-Spec Abschnitt 7.3)
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
    sections: list | None = None,
    downbeats: list[float] | None = None,
    pacing_map: dict | None = None,
) -> list[float]:
    """Phase 3+4: Waehlt Cut-Beats basierend auf DJ-Reglern und Sektion aus."""
    if not beats:
        return []

    downbeat_set: set[float] = set(downbeats) if downbeats else set()
    selected: list[float] = []
    beats_since_last_cut = 0

    for i, beat_time in enumerate(beats):
        if beat_time >= total_duration:
            break

        # Section-Kontext fuer diesen Beat ermitteln
        section_type = ""
        section_progress = 0.0
        if sections:
            sec = get_section_at_time(sections, beat_time)
            if sec is not None:
                section_type = sec.section_type
                sec_duration = max(sec.end - sec.start, 0.001)
                section_progress = (beat_time - sec.start) / sec_duration
                section_progress = max(0.0, min(1.0, section_progress))

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
            section_type=section_type,
            section_progress=section_progress,
            pacing_map=pacing_map,
            high_energy_behavior=settings.high_energy_behavior,
        )

        beats_since_last_cut += 1
        if beats_since_last_cut >= step:
            # Beat-Hierarchie: Grosse Steps bevorzugen Downbeats
            if step >= 8 and downbeat_set:
                # Nur auf Downbeats schneiden
                if beat_time in downbeat_set:
                    selected.append(beat_time)
                    beats_since_last_cut = 0
                # else: warten bis naechster Downbeat
            elif step >= 4 and downbeat_set:
                # Downbeat bevorzugen: falls vorhanden nehmen, sonst normal
                if beat_time in downbeat_set:
                    selected.append(beat_time)
                    beats_since_last_cut = 0
                else:
                    # Schauen ob naechster Beat ein Downbeat ist (1 Beat Toleranz)
                    next_beat = beats[i + 1] if i + 1 < len(beats) else None
                    if next_beat is None or next_beat not in downbeat_set:
                        selected.append(beat_time)
                        beats_since_last_cut = 0
            else:
                selected.append(beat_time)
                beats_since_last_cut = 0

    return selected


def _enforce_minimum_durations(
    cut_beats: list[float],
    sections: list | None,
    total_duration: float,
) -> list[float]:
    """Phase 2: Entfernt Cut-Beats die zu kurze Segmente erzeugen wuerden.

    - HARD_MIN_DURATION (3s) gilt immer
    - SECTION_MIN_DURATION gibt hoeheres Minimum pro Section-Type
    - Strukturgrenzen (DROP-Eintritt) werden nie entfernt
    """
    if len(cut_beats) < 3:
        return cut_beats

    # Strukturgrenzen-Set: Erste Beats von DROP/BUILDUP Sektionen schuetzen
    protected: set[int] = {0, len(cut_beats) - 1}  # Start und Ende nie entfernen
    if sections:
        for sec in sections:
            if sec.section_type in ("DROP", "BUILDUP"):
                # Finde naechsten Cut-Beat zur Sektionsgrenze
                for j, cb in enumerate(cut_beats):
                    if abs(cb - sec.start) < 1.0:
                        protected.add(j)
                        break

    result = [cut_beats[0]]  # Start immer behalten
    for i in range(1, len(cut_beats)):
        gap = cut_beats[i] - result[-1]

        # Section-spezifisches Minimum ermitteln
        min_dur = HARD_MIN_DURATION
        if sections:
            sec = get_section_at_time(sections, result[-1])
            if sec:
                min_dur = max(min_dur, SECTION_MIN_DURATION.get(sec.section_type, HARD_MIN_DURATION))

        if gap >= min_dur or i in protected:
            result.append(cut_beats[i])
        # else: Cut-Beat entfernen (Segment wird laenger)

    logger.info("Mindestdauer: %d → %d Cut-Beats (entfernt: %d)",
                len(cut_beats), len(result), len(cut_beats) - len(result))
    return result


SECTION_MOOD_QUERIES = {
    "DROP":       ["explosive energy", "bright lights", "intense fast motion", "crowd dancing"],
    "BREAKDOWN":  ["gentle scene", "soft lighting", "slow movement", "atmospheric calm"],
    "WARMUP":     ["calm landscape", "dark moody", "minimal abstract", "slow establishing"],
    "BUILDUP":    ["rising tension", "accelerating", "building energy", "upward motion"],
    "COOLDOWN":   ["peaceful", "serene nature", "fading", "gentle ending"],
    "TRANSITION": ["varied scenery", "moderate activity", "neutral"],
    "CHORUS":     ["vibrant performance", "colorful energy", "dancing"],
    "VERSE":      ["moderate movement", "storytelling", "detail shots"],
}

# ======================================================================
# AUD-82: Cross-Modal Audio-zu-Video Matching Engine
# ======================================================================

# Audio-Mood → Visual-Mood Mapping: Uebersetzt Audio-Eigenschaften in visuelle Praeferenzen
AUDIO_MOOD_TO_VISUAL = {
    "dark":        ["dark moody scene", "shadows", "low key lighting", "noir aesthetic"],
    "energetic":   ["bright vibrant colors", "fast motion", "dynamic camera", "crowd energy"],
    "melancholic": ["muted colors", "rain", "solitary figure", "desaturated tones"],
    "aggressive":  ["harsh contrasts", "rapid cuts", "intense red", "strobe effects"],
    "euphoric":    ["golden light", "sunrise", "celebration", "warm tones"],
    "dreamy":      ["soft focus", "pastel colors", "flowing movement", "ethereal glow"],
    "hypnotic":    ["repetitive patterns", "kaleidoscope", "geometric shapes", "tunnel vision"],
    "minimal":     ["clean lines", "negative space", "monochrome", "abstract geometry"],
}

# Section-spezifische Clip-Strategien: Definiert visuelle Praeferenzen pro Section-Type
SECTION_CLIP_STRATEGY = {
    "DROP": {
        "motion_range": (0.6, 1.0),   # Bevorzuge hohe Motion
        "contrast_boost": True,         # Kontrast zum vorherigen Clip belohnen
        "prefer_short_scenes": True,    # Kurze, impactvolle Szenen
        "energy_weight": 0.50,          # Energie-Match hoeher gewichtet
        "mood_weight": 0.20,
        "coherence_weight": 0.05,       # Bewusst niedrig — Impact > Kontinuitaet
        "freshness_weight": 0.15,
        "duration_weight": 0.10,
    },
    "BREAKDOWN": {
        "motion_range": (0.0, 0.35),   # Ruhige, langsame Clips
        "contrast_boost": False,
        "prefer_short_scenes": False,   # Laengere, atmosphaerische Szenen
        "energy_weight": 0.20,
        "mood_weight": 0.35,            # Stimmung wichtiger als Energie
        "coherence_weight": 0.25,       # Sanfte Uebergaenge
        "freshness_weight": 0.10,
        "duration_weight": 0.10,
    },
    "BUILDUP": {
        "motion_range": (0.3, 0.8),    # Steigend — Start ruhig, Ende dynamisch
        "contrast_boost": False,
        "prefer_short_scenes": False,
        "energy_weight": 0.35,
        "mood_weight": 0.25,
        "coherence_weight": 0.20,       # Visueller Aufbau braucht Kontinuitaet
        "freshness_weight": 0.10,
        "duration_weight": 0.10,
    },
    "WARMUP": {
        "motion_range": (0.05, 0.4),
        "contrast_boost": False,
        "prefer_short_scenes": False,
        "energy_weight": 0.20,
        "mood_weight": 0.30,
        "coherence_weight": 0.25,
        "freshness_weight": 0.10,
        "duration_weight": 0.15,
    },
    "COOLDOWN": {
        "motion_range": (0.0, 0.3),
        "contrast_boost": False,
        "prefer_short_scenes": False,
        "energy_weight": 0.15,
        "mood_weight": 0.35,
        "coherence_weight": 0.30,       # Sanftes Ausklingen
        "freshness_weight": 0.10,
        "duration_weight": 0.10,
    },
    "CHORUS": {
        "motion_range": (0.4, 0.9),
        "contrast_boost": False,
        "prefer_short_scenes": True,
        "energy_weight": 0.40,
        "mood_weight": 0.25,
        "coherence_weight": 0.15,
        "freshness_weight": 0.10,
        "duration_weight": 0.10,
    },
    "VERSE": {
        "motion_range": (0.2, 0.6),
        "contrast_boost": False,
        "prefer_short_scenes": False,
        "energy_weight": 0.25,
        "mood_weight": 0.30,
        "coherence_weight": 0.20,
        "freshness_weight": 0.10,
        "duration_weight": 0.15,
    },
    "TRANSITION": {
        "motion_range": (0.2, 0.7),
        "contrast_boost": False,
        "prefer_short_scenes": False,
        "energy_weight": 0.25,
        "mood_weight": 0.25,
        "coherence_weight": 0.25,
        "freshness_weight": 0.15,
        "duration_weight": 0.10,
    },
}

_DEFAULT_STRATEGY = SECTION_CLIP_STRATEGY["TRANSITION"]


@dataclass
class AudioContext:
    """Kompakter Audio-Kontext fuer Cross-Modal Matching."""
    bpm: float = 120.0
    mood: str = ""
    genre: str = ""
    key: str = ""
    avg_energy: float = 0.5
    drum_ratio: float = 0.4       # Drum-Energie / Gesamt (0-1)
    bass_ratio: float = 0.3       # Bass-Energie / Gesamt (0-1)
    vocal_ratio: float = 0.1      # Vocal-Energie / Gesamt (0-1)


class CrossModalMatcher:
    """Cross-Modal Audio-zu-Video Matching Engine (AUD-82, AUD-101).

    Verbindet Audio-Analyse mit Video-Selektion:
    - Audio-Mood → visuelle Stimmungs-Praeferenz (dark audio → dark visuals)
    - Stem-gewichtete Energie → Motion-Korrelation (RAFT)
    - Section-spezifische Clip-Strategien (Breakdown → ruhig, Drop → dynamisch)
    - Temporal Coherence via Sliding Window
    - AUD-101: Beat-Grid Alignment — belohnt Clips deren Szenen-Grenzen auf Beats fallen
    """

    def __init__(
        self,
        audio_ctx: AudioContext,
        mood_embeddings: dict[str, np.ndarray] | None = None,
        beats: list[float] | None = None,
    ):
        self.audio_ctx = audio_ctx
        self._mood_embeddings = mood_embeddings or {}
        self._audio_mood_embedding: np.ndarray | None = None
        self._recent_selections: list[dict] = []  # Sliding window fuer Temporal Coherence
        self._selection_window = 5  # Letzte N Clips fuer Glaettung
        # AUD-101: Beat-Grid fuer Scene-Beat Alignment Scoring
        self._beats_arr: np.ndarray | None = (
            np.array(beats, dtype=np.float64) if beats else None
        )

    def compute_audio_mood_embedding(self) -> np.ndarray | None:
        """Berechnet ein Audio-Mood-Embedding basierend auf Audio-Metadaten.

        Nutzt mood/genre/BPM/stem-Verhaeltnisse um visuelle Stimmungs-Queries zu generieren,
        dann SigLIP Text-Encoder fuer ein gewichtetes Embedding.
        """
        if self._audio_mood_embedding is not None:
            return self._audio_mood_embedding

        # Visuelle Queries aus Audio-Mood ableiten
        mood_queries = AUDIO_MOOD_TO_VISUAL.get(self.audio_ctx.mood, [])

        # BPM-basierte Stimmungs-Erweiterung
        if self.audio_ctx.bpm >= 140:
            mood_queries = mood_queries + ["high energy", "fast paced", "intense"]
        elif self.audio_ctx.bpm <= 90:
            mood_queries = mood_queries + ["slow movement", "ambient", "contemplative"]

        # Stem-basierte Erweiterung
        if self.audio_ctx.drum_ratio > 0.5:
            mood_queries = mood_queries + ["rhythmic motion", "percussion visual"]
        if self.audio_ctx.bass_ratio > 0.4:
            mood_queries = mood_queries + ["deep tones", "dark atmosphere", "sub bass visual"]
        if self.audio_ctx.vocal_ratio > 0.25:
            mood_queries = mood_queries + ["human presence", "portrait", "face close-up"]

        if not mood_queries:
            return None

        try:
            from services.video_analysis_service import texts_to_embeddings_batch
            embeddings = texts_to_embeddings_batch(mood_queries)
            if not embeddings:
                return None

            emb_list = list(embeddings.values())
            mean_emb = np.mean(emb_list, axis=0).astype(np.float32)
            mean_emb /= np.linalg.norm(mean_emb) + 1e-8
            self._audio_mood_embedding = mean_emb
            logger.info("Audio-Mood-Embedding berechnet (%d Queries, mood=%s, bpm=%.0f)",
                        len(mood_queries), self.audio_ctx.mood, self.audio_ctx.bpm)
            return mean_emb
        except (ImportError, ValueError, RuntimeError) as e:
            logger.warning("Audio-Mood-Embedding fehlgeschlagen: %s", e)
            return None

    def get_section_strategy(self, section_type: str) -> dict:
        """Gibt die Clip-Selektionsstrategie fuer einen Section-Type zurueck."""
        return SECTION_CLIP_STRATEGY.get(section_type, _DEFAULT_STRATEGY)

    def compute_motion_target(
        self,
        section_type: str,
        section_progress: float,
        energy_value: float,
    ) -> float:
        """Berechnet den Ziel-Motion-Score basierend auf Section + Audio-Energie.

        BUILDUP: Motion steigt mit section_progress (visueller Aufbau).
        DROP: Hohe Motion, leicht moduliert durch Audio-Energie.
        BREAKDOWN: Niedrige Motion, Fokus auf Atmosphaere.
        """
        strategy = self.get_section_strategy(section_type)
        lo, hi = strategy["motion_range"]

        if section_type == "BUILDUP":
            # Exponentieller Anstieg: Start bei lo, Ende bei hi
            t = section_progress ** 1.5
            base_target = lo + t * (hi - lo)
        elif section_type == "DROP":
            # Hohe Motion, Audio-Energie moduliert leicht
            base_target = lo + energy_value * (hi - lo)
        elif section_type in ("BREAKDOWN", "COOLDOWN", "WARMUP"):
            # Niedrige Motion, wenig Einfluss von Energie
            base_target = lo + energy_value * 0.3 * (hi - lo)
        else:
            # Standard: Linear nach Energie
            base_target = lo + energy_value * (hi - lo)

        # Stem-gewichtete Modulation: Drums treiben Motion hoch, Vocals daempfen
        drum_boost = (self.audio_ctx.drum_ratio - 0.3) * 0.2  # [-0.06, +0.14]
        vocal_dampen = (self.audio_ctx.vocal_ratio - 0.1) * -0.15  # [-0.06, +0.015]
        base_target = np.clip(base_target + drum_boost + vocal_dampen, 0.0, 1.0)

        return float(base_target)

    def compute_beat_sync_score(
        self,
        scene_start: float,
        scene_end: float,
        seg_start: float,
        tolerance: float = 0.08,
    ) -> float:
        """AUD-101: Bewertet wie gut die Szenen-Grenzen eines Clips auf Audio-Beats fallen.

        Ein Score von 1.0 bedeutet: Scene-Start faellt exakt auf einen Beat relativ
        zum Segment-Start. Misst die zeitliche Distanz zum naechsten Beat und
        bewertet mit Gauss-Falloff.

        Args:
            scene_start: Absoluter Zeitpunkt des Szenen-Starts im Video
            scene_end: Absoluter Zeitpunkt des Szenen-Endes im Video
            seg_start: Absoluter Zeitpunkt des Timeline-Segments (wo der Clip startet)
            tolerance: Max. Abweichung in Sekunden fuer perfekten Score (default ~2 Frames @25fps)

        Returns:
            Beat-Sync Score (0.0-1.0). 1.0 = perfekte Ausrichtung.
        """
        if self._beats_arr is None or len(self._beats_arr) == 0:
            return 0.5  # Neutral bei fehlendem Beat-Grid

        # Szenen-Dauer relativ zum Segment: wo wuerde der naechste Szenen-Cut fallen?
        scene_dur = scene_end - scene_start
        if scene_dur <= 0:
            return 0.5

        # Berechne: Zeitpunkte in der Audio-Timeline an denen Video-Szenen-Grenzen liegen
        # (= seg_start + N * scene_dur fuer N=1,2,... innerhalb des Beats-Range)
        boundary_scores = []
        # Pruefe den ersten Szenen-Uebergang nach dem Segment-Start
        t_boundary = seg_start + scene_dur
        max_check = min(seg_start + scene_dur * 4, self._beats_arr[-1])
        while t_boundary <= max_check and len(boundary_scores) < 4:
            # Naechsten Beat finden via bisect
            idx = np.searchsorted(self._beats_arr, t_boundary)
            best_dist = float("inf")
            for check_idx in (idx - 1, idx):
                if 0 <= check_idx < len(self._beats_arr):
                    dist = abs(self._beats_arr[check_idx] - t_boundary)
                    best_dist = min(best_dist, dist)
            # Gauss-Score: sigma = tolerance
            sync_score = float(np.exp(-0.5 * (best_dist / max(tolerance, 1e-6)) ** 2))
            boundary_scores.append(sync_score)
            t_boundary += scene_dur

        if not boundary_scores:
            return 0.5

        return float(np.mean(boundary_scores))

    def compute_cross_modal_fitness(
        self,
        clip_idx: int,
        section_type: str,
        section_progress: float,
        energy_value: float,
        motion_score: float,
        scene_duration: float,
        segment_duration: float,
        prev_clip_idx: int | None,
        clip_embeddings: np.ndarray,
        used_recently: list[int],
        fitness_matrix: dict[tuple, float],
        scene_start: float = 0.0,
        scene_end: float = 0.0,
        seg_start: float = 0.0,
    ) -> float:
        """Cross-Modal Fitness-Score mit section-spezifischer Gewichtung.

        Ersetzt die festen Gewichte aus _compute_clip_fitness durch dynamische,
        section-abhaengige Gewichte + Audio-Mood-Korrelation + Temporal Coherence.
        AUD-101: Integriert Beat-Sync Score fuer Szenen-Beat-Alignment.
        """
        strategy = self.get_section_strategy(section_type)

        # 1. Energy-Motion-Match (RAFT-korreliert)
        motion_target = self.compute_motion_target(section_type, section_progress, energy_value)
        # Gausssche Aehnlichkeit statt linearem Abstand — bestraft Abweichungen staerker
        motion_diff = motion_score - motion_target
        energy_match = float(np.exp(-2.0 * motion_diff ** 2))

        # 2. Mood-Match: Blende Section-Mood mit Audio-Mood
        section_mood = fitness_matrix.get((clip_idx, section_type), 0.5)
        audio_mood_score = 0.5
        if self._audio_mood_embedding is not None and clip_embeddings.shape[0] > clip_idx:
            clip_emb = clip_embeddings[clip_idx]
            norm = np.linalg.norm(clip_emb) + 1e-8
            audio_mood_score = float(np.dot(clip_emb / norm, self._audio_mood_embedding))
        # Mische: 60% Section-Mood, 40% Audio-Mood
        mood_match = section_mood * 0.6 + audio_mood_score * 0.4

        # 3. Visual Coherence mit Temporal Smoothing
        visual_coherence = 0.5
        if prev_clip_idx is not None and clip_embeddings.shape[0] > 0:
            if prev_clip_idx < clip_embeddings.shape[0] and clip_idx < clip_embeddings.shape[0]:
                a = clip_embeddings[prev_clip_idx]
                b = clip_embeddings[clip_idx]
                sim = float(np.dot(a, b) / ((np.linalg.norm(a) + 1e-8) * (np.linalg.norm(b) + 1e-8)))
                if strategy["contrast_boost"]:
                    visual_coherence = 1.0 - sim  # DROP: Kontrast = Impact
                else:
                    visual_coherence = sim

        # Temporal Coherence: Glaettung ueber letzte N Selektionen
        if self._recent_selections and not strategy["contrast_boost"]:
            recent_motions = [s["motion"] for s in self._recent_selections[-self._selection_window:]]
            avg_recent_motion = np.mean(recent_motions)
            # Bestrafe ploetzliche Motion-Spruenge (ausser bei DROP)
            motion_jump = abs(motion_score - avg_recent_motion)
            coherence_penalty = float(np.exp(-3.0 * motion_jump ** 2))
            visual_coherence = visual_coherence * 0.7 + coherence_penalty * 0.3

        # 4. Freshness
        if clip_idx in used_recently[-3:]:
            freshness = 0.0
        elif clip_idx in used_recently[-5:]:
            freshness = 0.3
        else:
            freshness = 1.0

        # 5. Duration-Fit
        if segment_duration > 0:
            ratio = min(scene_duration, segment_duration) / max(scene_duration, segment_duration)
            duration_fit = ratio
            # Strategie-Praeferenz: Kurze Szenen fuer DROPs
            if strategy["prefer_short_scenes"] and scene_duration < segment_duration * 0.8:
                duration_fit = min(1.0, duration_fit + 0.2)
        else:
            duration_fit = 0.5

        # 6. AUD-101: Beat-Sync Score — belohnt Clips deren Szenen-Grenzen auf Beats fallen
        beat_sync = self.compute_beat_sync_score(scene_start, scene_end, seg_start)

        # Section-spezifische Gewichtung (AUD-101: beat_sync anteilig aus duration_weight)
        # Beat-Sync ist am wichtigsten bei DROPs (harte Cuts) und BUILDUPs
        beat_sync_weight = 0.08 if section_type in ("DROP", "BUILDUP") else 0.05
        # Reduziere duration_weight proportional um beat_sync_weight einzufuegen
        adj_duration_weight = max(0.0, strategy["duration_weight"] - beat_sync_weight)

        score = (
            strategy["energy_weight"] * energy_match
            + strategy["mood_weight"] * mood_match
            + strategy["coherence_weight"] * visual_coherence
            + strategy["freshness_weight"] * freshness
            + adj_duration_weight * duration_fit
            + beat_sync_weight * beat_sync
        )

        return float(score)

    def record_selection(self, clip_idx: int, motion_score: float, section_type: str) -> None:
        """Registriert eine Clip-Selektion fuer Temporal Coherence Tracking."""
        self._recent_selections.append({
            "clip_idx": clip_idx,
            "motion": motion_score,
            "section": section_type,
        })
        # Begrenze auf 2x Fenstergroesse
        if len(self._recent_selections) > self._selection_window * 2:
            self._recent_selections = self._recent_selections[-self._selection_window * 2:]


def _precompute_mood_embeddings() -> dict[str, np.ndarray]:
    """Berechnet SigLIP Text-Embeddings fuer alle Section-Mood-Queries.

    Laedt SigLIP EINMAL, berechnet alle ~24 Queries als Batch, entlaedt sofort.
    Returns: dict[section_type, 1152-dim mean embedding]
    """
    from services.video_analysis_service import texts_to_embeddings_batch

    # Alle Queries flach sammeln
    all_queries = []
    query_to_section: dict[str, str] = {}
    for section_type, queries in SECTION_MOOD_QUERIES.items():
        for q in queries:
            all_queries.append(q)
            query_to_section[q] = section_type

    # Batch-Embedding (1x SigLIP load)
    embeddings = texts_to_embeddings_batch(all_queries)
    if not embeddings:
        logger.warning("Mood-Embeddings konnten nicht berechnet werden (SigLIP nicht verfuegbar)")
        return {}

    # Pro Section mitteln
    section_embeddings: dict[str, list[np.ndarray]] = {}
    for query, emb in embeddings.items():
        sec = query_to_section.get(query)
        if sec:
            section_embeddings.setdefault(sec, []).append(emb)

    result: dict[str, np.ndarray] = {}
    for sec, embs in section_embeddings.items():
        mean_emb = np.mean(embs, axis=0).astype(np.float32)
        mean_emb /= np.linalg.norm(mean_emb) + 1e-8
        result[sec] = mean_emb

    logger.info("Mood-Embeddings: %d Section-Types berechnet", len(result))
    return result


def _precompute_clip_fitness_matrix(
    mood_embeddings: dict[str, np.ndarray],
    clip_embeddings: np.ndarray,
    clip_metadata: list[dict],
) -> dict[tuple, float]:
    """Berechnet Mood-Similarity fuer jede (Clip, Section) Kombination.

    Reine CPU-Operation (numpy cosine similarity), kein VRAM noetig.
    Returns: dict[(clip_idx, section_type), similarity_float]
    """
    if not mood_embeddings or clip_embeddings.shape[0] == 0:
        return {}

    # Normalize clip embeddings
    norms = np.linalg.norm(clip_embeddings, axis=1, keepdims=True) + 1e-8
    clip_normed = clip_embeddings / norms

    matrix: dict[tuple, float] = {}
    for section_type, mood_emb in mood_embeddings.items():
        # Cosine similarity: all clips vs this section's mood vector
        similarities = clip_normed @ mood_emb  # shape: (N,)
        for i, sim in enumerate(similarities):
            matrix[(i, section_type)] = float(sim)

    logger.info("Fitness-Matrix: %d Eintraege (%d Clips x %d Sections)",
                len(matrix), clip_embeddings.shape[0], len(mood_embeddings))
    return matrix


def _compute_clip_fitness(
    clip_idx: int,
    section_type: str,
    energy_value: float,
    motion_score: float,
    scene_duration: float,
    segment_duration: float,
    prev_clip_idx: int | None,
    clip_embeddings: np.ndarray,
    used_recently: list[int],
    fitness_matrix: dict[tuple, float],
) -> float:
    """Multi-dimensionales Fitness-Scoring fuer einen Clip-Kandidaten.

    fitness = 0.30 * energy_match + 0.25 * mood_match
            + 0.15 * visual_continuity + 0.15 * freshness + 0.15 * duration_fit
    """
    # 1. Energy-Match: Wie gut passt Motion-Score zur Musik-Energie
    energy_match = 1.0 - abs(motion_score - energy_value)

    # 2. Mood-Match: Pre-computed SigLIP similarity
    mood_match = fitness_matrix.get((clip_idx, section_type), 0.5)

    # 3. Visual Continuity: Cosine-Sim zum vorherigen Clip
    visual_cont = 0.5  # Default bei keinem Vorgaenger
    if prev_clip_idx is not None and clip_embeddings.shape[0] > 0:
        if prev_clip_idx < clip_embeddings.shape[0] and clip_idx < clip_embeddings.shape[0]:
            a = clip_embeddings[prev_clip_idx]
            b = clip_embeddings[clip_idx]
            norm_a = np.linalg.norm(a) + 1e-8
            norm_b = np.linalg.norm(b) + 1e-8
            sim = float(np.dot(a, b) / (norm_a * norm_b))
            # DROP: Kontrast belohnen (invertieren), sonst Kontinuitaet
            if section_type == "DROP":
                visual_cont = 1.0 - sim  # Kontrast = Impact
            else:
                visual_cont = sim

    # 4. Freshness: Wie lange seit letzter Verwendung
    vid_id = clip_idx  # Mapping via caller
    if vid_id in used_recently[-5:]:
        freshness = 0.0 if vid_id in used_recently[-3:] else 0.3
    else:
        freshness = 1.0

    # 5. Duration-Fit: Natuerliche Laenge passt zum Slot
    if segment_duration > 0:
        ratio = min(scene_duration, segment_duration) / max(scene_duration, segment_duration)
        duration_fit = ratio  # 1.0 = perfekter Fit
    else:
        duration_fit = 0.5

    return (0.30 * energy_match + 0.25 * mood_match + 0.15 * visual_cont
            + 0.15 * freshness + 0.15 * duration_fit)


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

    # F-008 Fix: Additional safety check for empty candidates list
    if not candidates:
        logger.error("_match_video_by_motion: candidates is empty after fallback (should not happen)")
        return -1, 0.0

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
    section_type: str = "",
    fitness_matrix: dict[tuple, float] | None = None,
    clip_embeddings: np.ndarray | None = None,
    clip_metadata: list[dict] | None = None,
    prev_clip_idx: int | None = None,
    cross_modal_matcher: CrossModalMatcher | None = None,
    section_progress: float = 0.0,
    pipeline: Any = None,
) -> tuple[int, float, int | None]:
    """Waehlt den besten Video-Clip fuer ein Segment.

    Phase 3: Multi-dimensionales Fitness-Scoring mit SigLIP Mood-Matching.
    AUD-82: Cross-Modal Matching wenn CrossModalMatcher verfuegbar.
    T6.4: Integration der PacingPipeline (4-stage selection).
    Fallback: Motion-Score Matching wenn keine Embeddings verfuegbar.

    Returns: (video_id, source_start, clip_idx_in_matrix)
    """
    seg_duration = seg_end - seg_start

    # F-007 Fix: Berechne Audio-Energie am Segment-Mittelpunkt, warne bei Fallback
    if energy_per_beat and beats:
        seg_mid = (seg_start + seg_end) / 2.0
        beat_idx = int(np.searchsorted(np.array(beats), seg_mid))
        beat_idx = min(beat_idx, len(energy_per_beat) - 1)
        if beat_idx >= 0:
            energy_value = energy_per_beat[beat_idx]
        else:
            energy_value = 0.5
            logger.warning("F-007: Segment energy fallback 0.5 (beat_idx=%d < 0)", beat_idx)
    else:
        energy_value = 0.5
        logger.warning("F-007: Segment energy fallback 0.5 (energy_per_beat=%s, beats=%s)",
                      "None" if energy_per_beat is None else f"len={len(energy_per_beat)}",
                      "None" if beats is None else f"len={len(beats)}")

    # KI-Gedaechtnis einblenden
    memory_bias_val = 0.0
    if memory_bias is not None:
        pref_motion = memory_bias.get("preferred_motion")
        if pref_motion is not None:
            energy_value = energy_value * 0.6 + pref_motion * 0.4
            memory_bias_val = 0.5 # Default bias if memory exists

    # T6.4: Integration der neuen PacingPipeline
    if pipeline is not None and clip_metadata:
        context = {
            "energy": energy_value,
            "section_type": section_type,
            "section_progress": section_progress,
            "vocal_active": False, # TODO: Vocal activity einbinden
            "memory_bias": memory_bias_val,
            "prev_embedding": None # TODO: Prev embedding einbinden
        }
        
        # Mapping: video_path → video_id (benötigt für Pipeline-Resultate)
        path_to_vid = {info["path"]: vid for vid, info in video_info.items()}
        
        # Kandidaten vorbereiten (mit Embeddings falls verfügbar)
        pipeline_candidates = []
        for i, meta in enumerate(clip_metadata):
            vid = path_to_vid.get(meta["video_path"])
            if vid is None or vid not in available_ids:
                continue
            
            c_data = meta.copy()
            c_data["video_clip_id"] = vid
            if clip_embeddings is not None and i < len(clip_embeddings):
                c_data["embedding"] = clip_embeddings[i]
            
            # Cross-modal fitness score falls verfügbar als Basis-Fitness nutzen
            if cross_modal_matcher:
                c_data["fitness_score"] = cross_modal_matcher.compute_cross_modal_fitness(
                    clip_idx=i,
                    section_type=section_type,
                    section_progress=section_progress,
                    energy_value=energy_value,
                    motion_score=meta.get("motion_score", 0.5),
                    scene_duration=meta["scene_end"] - meta["scene_start"],
                    segment_duration=seg_duration,
                    prev_clip_idx=prev_clip_idx,
                    clip_embeddings=clip_embeddings,
                    used_recently=used_recently,
                    fitness_matrix=fitness_matrix or {},
                    scene_start=meta["scene_start"],
                    scene_end=meta["scene_end"],
                    seg_start=seg_start,
                )
            pipeline_candidates.append(c_data)
            
        best = pipeline.select_best_scene(pipeline_candidates, context)
        if best:
            # clip_idx_in_matrix finden
            best_idx = None
            for i, meta in enumerate(clip_metadata):
                if meta["video_path"] == best["video_path"] and meta["scene_start"] == best["scene_start"]:
                    best_idx = i
                    break
            return best["video_clip_id"], best["scene_start"], best_idx

    # Phase 3 + AUD-82: Multi-dimensionales Fitness-Scoring (Legacy Fallback)
    if fitness_matrix and clip_metadata and clip_embeddings is not None and clip_embeddings.shape[0] > 0:
        # Mapping: video_path → video_id
        path_to_vid: dict[str, int] = {}
        for vid, info in video_info.items():
            path_to_vid[info["path"]] = vid

        best_score = -1.0
        best_vid = -1
        best_source_start = 0.0
        best_clip_idx = None
        best_motion = 0.5

        for clip_idx, meta in enumerate(clip_metadata):
            vid = path_to_vid.get(meta["video_path"])
            if vid is None or vid not in available_ids:
                continue

            scene_duration = meta["scene_end"] - meta["scene_start"]
            motion = meta.get("motion_score", 0.5)

            # AUD-82 + AUD-101: Cross-Modal Scoring mit Beat-Sync
            if cross_modal_matcher is not None:
                score = cross_modal_matcher.compute_cross_modal_fitness(
                    clip_idx=clip_idx,
                    section_type=section_type,
                    section_progress=section_progress,
                    energy_value=energy_value,
                    motion_score=motion,
                    scene_duration=scene_duration,
                    segment_duration=seg_duration,
                    prev_clip_idx=prev_clip_idx,
                    clip_embeddings=clip_embeddings,
                    used_recently=used_recently,
                    fitness_matrix=fitness_matrix,
                    scene_start=meta["scene_start"],
                    scene_end=meta["scene_end"],
                    seg_start=seg_start,
                )
            else:
                score = _compute_clip_fitness(
                    clip_idx=clip_idx,
                    section_type=section_type,
                    energy_value=energy_value,
                    motion_score=motion,
                    scene_duration=scene_duration,
                    segment_duration=seg_duration,
                    prev_clip_idx=prev_clip_idx,
                    clip_embeddings=clip_embeddings,
                    used_recently=used_recently,
                    fitness_matrix=fitness_matrix,
                )

            if score > best_score:
                best_score = score
                best_vid = vid
                best_source_start = meta["scene_start"]
                best_clip_idx = clip_idx
                best_motion = motion

        if best_vid != -1:
            # AUD-82: Selektion im Matcher registrieren fuer Temporal Coherence
            if cross_modal_matcher is not None and best_clip_idx is not None:
                cross_modal_matcher.record_selection(best_clip_idx, best_motion, section_type)
            return best_vid, best_source_start, best_clip_idx

    # Fallback: Vibe-Keyword Suche
    if vibe and vibe.strip():
        try:
            from services.video_analysis_service import search_videos_by_text
            results = search_videos_by_text(vibe.strip(), top_k=5)
            if results:
                for r in results:
                    r_path = r.get("video_path", "")
                    for vid, info in video_info.items():
                        if info["path"] == r_path:
                            return vid, r.get("scene_start", 0.0), None
        except (ImportError, ValueError, RuntimeError) as e:
            logger.warning("Semantic Suche fehlgeschlagen: %s", e)

    # Fallback: Motion-basiertes Matching
    vid, source_start = _match_video_by_motion(
        energy_value, video_info, available_ids, used_recently,
    )
    if source_start == 0.0:
        source_start = clip_offsets.get(vid, 0.0)
    return vid, source_start, None


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
        clip = session.get(VideoClip, video_id, options=[joinedload(VideoClip.scenes)])
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
