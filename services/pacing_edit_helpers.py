"""Pacing Edit Helpers — Kandidaten-Auswahl, Clip-Scoring und Keyframe-Generierung.

Enthält:
- Fortgeschrittene Cut-Beat-Auswahl (_compute_effective_step, _select_cut_beats_advanced)
- Mindestdauer-Erzwingung (_enforce_minimum_durations)
- Multi-dimensionales Clip-Fitness-Scoring (_precompute_mood_embeddings, _compute_clip_fitness)
- Clip-Matching (_match_video_for_segment, _match_video_by_motion)
- Keyframe-String-Generator (generate_keyframe_string, generate_keyframe_strings_for_project)

Hinweis: calculate_cut_points / calculate_drum_cuts leben in pacing_service.py
um Test-Mocking via patch.object(svc, ...) zu unterstuetzen.
"""

from __future__ import annotations

import logging
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
) -> int:
    """Berechnet den effektiven Beat-Schritt fuer einen bestimmten Beat.

    Kombiniert:
    - base_cut_rate (aus UI)
    - section_type / section_progress (SECTION_PACING_MAP, Phase 1+4)
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
    energy = 0.5
    energy_step = effective
    if reactivity > 0 and beat_index < len(energy_per_beat):
        energy = energy_per_beat[beat_index]

        # Hohe Energie (>0.7): Step reduzieren (mehr Cuts)
        if energy > 0.7:
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
) -> tuple[int, float, int | None]:
    """Waehlt den besten Video-Clip fuer ein Segment.

    Phase 3: Multi-dimensionales Fitness-Scoring mit SigLIP Mood-Matching.
    Fallback: Motion-Score Matching wenn keine Embeddings verfuegbar.

    Returns: (video_id, source_start, clip_idx_in_matrix)
    """
    seg_duration = seg_end - seg_start

    # Berechne Audio-Energie am Segment-Mittelpunkt
    energy_value = 0.5
    if energy_per_beat and beats:
        seg_mid = (seg_start + seg_end) / 2.0
        beat_idx = int(np.searchsorted(np.array(beats), seg_mid))
        beat_idx = min(beat_idx, len(energy_per_beat) - 1)
        if beat_idx >= 0:
            energy_value = energy_per_beat[beat_idx]

    # KI-Gedaechtnis einblenden
    if memory_bias is not None:
        pref_motion = memory_bias.get("preferred_motion")
        if pref_motion is not None:
            energy_value = energy_value * 0.6 + pref_motion * 0.4

    # Phase 3: Multi-dimensionales Fitness-Scoring
    if fitness_matrix and clip_metadata and clip_embeddings is not None and clip_embeddings.shape[0] > 0:
        # Mapping: video_path → video_id
        path_to_vid: dict[str, int] = {}
        for vid, info in video_info.items():
            path_to_vid[info["path"]] = vid

        best_score = -1.0
        best_vid = -1
        best_source_start = 0.0
        best_clip_idx = None

        for clip_idx, meta in enumerate(clip_metadata):
            vid = path_to_vid.get(meta["video_path"])
            if vid is None or vid not in available_ids:
                continue

            scene_duration = meta["scene_end"] - meta["scene_start"]
            motion = meta.get("motion_score", 0.5)

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

        if best_vid != -1:
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
        except Exception as e:
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
