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

import numpy as np

from services.pacing.scorer import AudioContext, ClipFeatures


def _clamp01(v: float) -> float:
    return float(max(0.0, min(1.0, v)))


def _safe_attr(obj, name, default=None):
    return getattr(obj, name, default)


def build_audio_context(
    seg_start_sec: float,
    seg_section_type: str | None,
    audio_track,
    beats,
    energy_per_beat: Iterable[float] | None,
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

    # Harmonic-Tension aus Energy ableiten (wenn track.harmonic_tension nicht da)
    track_tension = _safe_attr(audio_track, "harmonic_tension", None)
    if track_tension is not None:
        tension = _clamp01(float(track_tension))
    elif energy_val is not None:
        # Heuristik: Tension steigt ab energy >= 0.5 stärker als linear
        tension = _clamp01(energy_val ** 0.85)
    else:
        tension = None

    section_lower = seg_section_type.strip().lower() if seg_section_type else None

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
        at_groove_template=_safe_attr(audio_track, "groove_template", None),
        at_lufs=_safe_attr(audio_track, "lufs", None),
    )


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

    return ClipFeatures(
        clip_id=int(video_clip_id),
        scene_id=scene_id,
        role=str(role),
        mood_refined=str(mood),
        style_bucket_id=int(bucket),
        motion_score=motion,
        embedding=embedding,
    )
