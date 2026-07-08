"""P1.1 / Cycle 11: Mapping zwischen `auto_edit_phase3` Cut-Loop und
`PacingPipeline.select_best`.

Pure Funktionen — keine DB-Calls, keine GPU-Direktzugriffe. Caller muss
die DB-Daten (audio_track, scenes, clip_offsets, ...) bereits aufgelöst
übergeben.

Wird von `services/pacing/bridge.py:maybe_use_studio_brain_pipeline()`
konsumiert, sobald das Feature-Flag aktiv ist.
"""
from __future__ import annotations

from typing import Iterable

import logging

import numpy as np

from services.pacing.scorer import AudioContext, ClipFeatures


def _clamp01(v: float) -> float:
    return float(max(0.0, min(1.0, v)))


def _safe_attr(obj, name, default=None):
    return getattr(obj, name, default)


logger = logging.getLogger(__name__)


def build_audio_context(
    seg_start_sec: float,
    seg_section_type: str | None,
    audio_track,
    beats,
    energy_per_beat: Iterable[float] | None,
    stem_energies: dict | None = None,
    dominant_stem: str | None = None,
) -> AudioContext:
    """Baut einen AudioContext-Snapshot für einen Cut-Punkt.

    Args:
        seg_start_sec: Cut-Zeitpunkt in Sekunden.
        seg_section_type: Section-Name aus structure_detection
            ("intro", "drop", ...). Wird auf lowercase gemappt.
        audio_track: ORM-AudioTrack mit Attributen bpm/key/mood/genre/...
        beats: Beat-Timestamps (np.ndarray oder Liste).
        energy_per_beat: Energie pro Beat (gleich lang wie beats), oder None.

    Returns:
        AudioContext-Dataclass mit allen 14 at_*-Feldern.
    """
    energy_list = list(energy_per_beat) if energy_per_beat is not None else []

    # Beat-Index per binär-Suche
    beats_arr = np.asarray(beats, dtype=np.float64)
    if beats_arr.size == 0:
        beat_idx = 0
    else:
        beat_idx = int(np.searchsorted(beats_arr, seg_start_sec, side="right") - 1)
        beat_idx = max(0, beat_idx)

    if energy_list:
        clamped = min(beat_idx, len(energy_list) - 1)
        energy_val = _clamp01(float(energy_list[clamped]))
    else:
        energy_val = None

    # Harmonic-Tension: Cycle 14 Option A — Reihenfolge der Quellen:
    # 1. Skalar-Spalte audio_track.harmonic_tension (neue Migration b2c3d4e5f6a7)
    # 2. Curve[beat_idx] aus harmonic_tension_curve
    # 3. Energy-basierte Heuristik
    track_tension = _safe_attr(audio_track, "harmonic_tension", None)
    if track_tension is None:
        tension_curve = _safe_attr(audio_track, "harmonic_tension_curve", None)
        if tension_curve and energy_list:
            try:
                idx_in_curve = min(beat_idx, len(tension_curve) - 1)
                track_tension = float(tension_curve[idx_in_curve])
            except (TypeError, IndexError, ValueError):
                track_tension = None
    if track_tension is not None:
        tension = _clamp01(float(track_tension))
    elif energy_val is not None:
        # Heuristik: Tension steigt ab energy >= 0.5 stärker als linear
        tension = _clamp01(energy_val ** 0.85)
    else:
        tension = None

    section_lower = seg_section_type.strip().lower() if seg_section_type else None

    # Cycle 14 Option A: groove_template lebt auf Beatgrid (FK von AudioTrack),
    # nicht direkt auf AudioTrack. Beatgrid wird via lazy='joined' eager
    # geladen, also ist .beatgrid.groove_template ohne extra-Query verfügbar.
    groove_template = None
    beatgrid = _safe_attr(audio_track, "beatgrid", None)
    if beatgrid is not None:
        groove_template = _safe_attr(beatgrid, "groove_template", None)

    return AudioContext(
        at_timestamp_sec=float(seg_start_sec),
        at_beat_idx=beat_idx if energy_list else None,
        at_section_type=section_lower,
        at_bpm=_safe_attr(audio_track, "bpm", None),
        at_energy=energy_val,
        at_key=_safe_attr(audio_track, "key", None),
        at_key_confidence=_safe_attr(audio_track, "key_confidence", None),
        at_harmonic_tension=tension,
        at_mood_audio=_safe_attr(audio_track, "mood", None),
        at_mood_video=_safe_attr(audio_track, "mood", None),
        at_genre=_safe_attr(audio_track, "genre", None),
        at_sub_genre=_safe_attr(audio_track, "sub_genre", None),
        at_spectral_hash=_safe_attr(audio_track, "spectral_hash", None),
        at_groove_template=groove_template,
        at_lufs=_safe_attr(audio_track, "lufs", None),
        # NEUBAU-VOLLINTEGRATION T2.5.4: Stem-Kontext + Audio-Mood-Vektor.
        # audio_mood_vector braucht Shot-Klassen-Centroids (SigLIP-Text,
        # prozess-gecacht); ohne Centroids/Stems bleiben die Felder None
        # und der Scorer nutzt seine Fallback-Terme.
        at_stem_energies=stem_energies,
        at_dominant_stem=dominant_stem,
        at_audio_mood_vec=_build_audio_mood_vec(stem_energies, section_lower),
    )


def _build_audio_mood_vec(stem_energies: dict | None, section_type: str | None):
    if not stem_energies:
        return None
    try:
        from services.pacing.audio_mood_vector import compute_audio_mood_vector
        from services.pacing.shot_centroids import get_shot_class_centroids
        centroids = get_shot_class_centroids()
        if not centroids:
            return None
        vec = compute_audio_mood_vector(stem_energies, section_type, centroids)
        return vec
    except Exception as exc:  # defensiv: Kontextbau darf nie crashen
        logger.debug("audio_mood_vec nicht berechenbar: %s", exc)
        return None


def build_clip_features(video_clip_id: int, scene) -> ClipFeatures:
    """Baut ClipFeatures aus einer (anchor-)Scene + Video-Clip-ID.

    Args:
        video_clip_id: ID des VideoClips (FK).
        scene: ORM-Scene oder Stub mit Feldern id/motion_score/energy/
            ai_mood/role/style_bucket_id/embedding.

    Returns:
        ClipFeatures-Dataclass für PacingPipeline.
    """
    scene_id = int(_safe_attr(scene, "id", 0))

    # Motion-Score: bevorzugt scene.motion_score, sonst scene.energy
    raw_motion = _safe_attr(scene, "motion_score", None)
    if raw_motion is None:
        raw_motion = _safe_attr(scene, "energy", 0.5)
    motion = _clamp01(float(raw_motion))

    role = _safe_attr(scene, "role", None) or "unknown"
    mood = _safe_attr(scene, "ai_mood", None) or _safe_attr(scene, "mood_refined", None) or "unknown"
    bucket = _safe_attr(scene, "style_bucket_id", None)
    if bucket is None:
        bucket = 0  # Sentinel für unbekannten Style-Bucket

    embedding = _safe_attr(scene, "embedding", None)
    # Falls embedding bytes/list ist, in np.float32-Array wandeln
    if embedding is not None and not isinstance(embedding, np.ndarray):
        try:
            embedding = np.asarray(embedding, dtype=np.float32)
        except (TypeError, ValueError):
            embedding = None

    # NEUBAU-VOLLINTEGRATION T2.5.5 (FR-S2-1): Shot-Klassen-Konfidenzen.
    # Entweder vom Caller vorberechnet (scene.shot_confidences) oder — wenn
    # ein Embedding + Centroids vorliegen — hier on-the-fly klassifiziert.
    shot_conf = _safe_attr(scene, "shot_confidences", None)
    if shot_conf is None and embedding is not None:
        try:
            from services.pacing.shot_centroids import get_shot_class_centroids
            from services.pacing.shot_type_classifier import classify
            _cents = get_shot_class_centroids()
            if _cents:
                shot_conf = classify(embedding, _cents)
        except Exception as exc:  # defensiv: Feature-Bau darf nie crashen
            logger.debug("shot_confidences nicht berechenbar: %s", exc)
            shot_conf = None

    return ClipFeatures(
        clip_id=int(video_clip_id),
        scene_id=scene_id,
        role=str(role),
        mood_refined=str(mood),
        style_bucket_id=int(bucket),
        motion_score=motion,
        embedding=embedding,
        shot_confidences=shot_conf,
    )
