from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import yaml  # PyYAML already in the project via alembic

from services.stats.wilson_lower_bound import wilson_lower_bound

# ── Public data-transfer types ──────────────────────────────────────────────


@dataclass(frozen=True)
class ClipFeatures:
    """All per-clip features needed by the scorer. Order is value-only
    (no DB/SQLAlchemy coupling)."""

    clip_id: int
    scene_id: int
    role: str  # hero|action|transition|detail|establishing|filler|unknown
    mood_refined: str  # one of 10 MoodAnchorMatcher classes
    style_bucket_id: int  # reference into struct_style_bucket
    motion_score: float  # 0..1
    # Optional: embedding for spectral_fit / style_compat when the caller has it cached.
    # Absent = term returns 0.0 (neutral).
    embedding: np.ndarray | None = None


@dataclass(frozen=True)
class AudioContext:
    """Snapshot of audio features at the cut-point. Matches the fields in
    `mem_decision.at_*` per Design §4.2.
    """

    at_timestamp_sec: float
    at_beat_idx: int | None
    at_section_type: (
        str | None
    )  # intro|buildup|drop|breakdown|outro|verse|chorus|bridge|transition
    at_bpm: float | None
    at_energy: float | None  # 0..1
    at_key: str | None  # musical key
    at_key_confidence: float | None
    at_harmonic_tension: float | None  # 0..1
    at_mood_audio: str | None  # energetic|calm|dramatic|ambient
    at_mood_video: (
        str | None
    )  # redundant channel; from audio-derived visual hint if any
    at_genre: str | None
    at_sub_genre: str | None
    at_spectral_hash: str | None  # 8-band signature hash
    at_groove_template: str | None
    at_lufs: float | None


# ── Scoring helper functions (pure — no DB/IO) ──────────────────────────────

# These return values in [0, 1] for positive terms, or [0, 1] representing
# a penalty magnitude that gets multiplied by the weight and subtracted.


def role_fit(section_type: str | None, clip_role: str) -> float:
    """1.0 if clip_role is plausible for the section; 0.3 if tolerated; 0.0 if
    mismatched. Hard-rules (Section×Role matrix) are in config/pacing_rules.yaml
    — this function uses a lighter in-module default because the scorer runs
    AFTER Stage 1 (Hard Rules) has already filtered. See Design §6.2."""
    if not section_type:
        return 0.5  # unknown section → neutral
    section = section_type.lower()
    # Preferred pairings — the positive majority
    preferred: dict[str, set[str]] = {
        "drop": {"hero", "action"},
        "buildup": {"hero", "action", "transition"},
        "intro": {"establishing", "ambient", "detail"},
        "outro": {"establishing", "detail", "ambient"},
        "breakdown": {"detail", "ambient", "establishing"},
        "chorus": {"hero", "action"},
        "verse": {"hero", "detail"},
        "bridge": {"transition", "detail"},
        "warmup": {"establishing", "hero", "detail"},
        "transition": {"transition", "action", "hero"},
    }
    allowed = preferred.get(section, set())
    if clip_role in allowed:
        return 1.0
    if clip_role == "filler" or clip_role == "unknown":
        return 0.3
    return 0.0


def style_compat(predecessor: ClipFeatures | None, clip: ClipFeatures) -> float:
    """Cosine similarity of embeddings if both present; otherwise 0.5 (neutral).
    NOT a penalty — just similarity. The collision-penalty term handles the
    negative side.

    B-217: norms are looked up via _embedding_norm() — a content-keyed
    cache (NOT id-based) so a 500-candidate pool with identical
    predecessor only computes the predecessor's norm once. The cache
    key uses the array's leading bytes as content fingerprint, making
    it GC-safe (id reuse after free does NOT cause wrong hits)."""
    if predecessor is None or predecessor.embedding is None or clip.embedding is None:
        return 0.5
    a = predecessor.embedding
    b = clip.embedding
    na = _embedding_norm(a)
    nb = _embedding_norm(b)
    if na < 1e-9 or nb < 1e-9:
        return 0.5
    return float(np.dot(a, b) / (na * nb))


# B-217: Content-keyed L2-norm cache. The key is built from a small
# leading slice of the array's bytes plus its shape — fast (<1µs) and
# unambiguous: two different float32 arrays virtually never share their
# first 32 bytes. The cache is bounded; on overflow it is cleared.
# Crucially, this is NOT id()-based — id reuse after GC cannot poison
# the cache, so determinism (e.g. golden-snapshot) is preserved.
_NORM_CACHE: dict[tuple[bytes, tuple[int, ...], str], float] = {}
_NORM_CACHE_MAX = 4096


def _embedding_norm(arr: np.ndarray) -> float:
    """L2-norm with content-keyed cache. Safe across array GC.

    Fingerprint: first 8 elements as bytes (~32 bytes copy — sub-µs).
    For two distinct float32 1152-d arrays the chance of identical
    leading 8 floats is astronomically low (8 * 32 = 256 bits of entropy).
    """
    # Use a contiguous slice and a small slice — avoids copying the full array.
    # arr[:8].tobytes() copies at most 8 elements, not the whole 1152-d vector.
    fingerprint = arr[:8].tobytes() if arr.size >= 8 else arr.tobytes()
    key = (fingerprint, arr.shape, str(arr.dtype))
    cached = _NORM_CACHE.get(key)
    if cached is not None:
        return cached
    val = float(np.linalg.norm(arr))
    if len(_NORM_CACHE) >= _NORM_CACHE_MAX:
        _NORM_CACHE.clear()
    _NORM_CACHE[key] = val
    return val


def mood_match(audio_mood: str | None, clip_mood: str) -> float:
    """1.0 for exact match, 0.6 for same family, 0.0 otherwise.

    Family groupings (Research §Q6 + Design §5.2 Step 2):
        energetic → euphoric, aggressive, uplifting
        calm      → calm, ambient, dreamy
        dramatic  → dark, tense, aggressive
        ambient   → ambient, dreamy, calm
        euphoric  → euphoric (for when mood_video is already refined)
        ... (refined classes match only themselves at 1.0)
    """
    if not audio_mood:
        return 0.5
    if audio_mood == clip_mood:
        return 1.0
    FAMILY: dict[str, frozenset[str]] = {
        "energetic": frozenset({"euphoric", "aggressive", "uplifting"}),
        "calm": frozenset({"calm", "ambient", "dreamy"}),
        "dramatic": frozenset({"dark", "tense", "aggressive"}),
        "ambient": frozenset({"ambient", "dreamy", "calm"}),
    }
    if clip_mood in FAMILY.get(audio_mood, frozenset()):
        return 0.6
    return 0.0


def genre_prior(
    audio_genre: str | None,
    clip_style_bucket_id: int,
    pattern_lookup: Callable[[str, str, int], float] | None = None,
) -> float:
    """Learned prior: how often has this style_bucket been accepted for this genre?
    Pulled from memory via `pattern_lookup`. Unseen → 0.5 (Wilson-neutral).
    """
    if audio_genre is None or pattern_lookup is None:
        return 0.5
    return pattern_lookup("genre", audio_genre, clip_style_bucket_id)


def key_prior(
    audio_key: str | None,
    clip_mood: str,
    pattern_lookup: Callable[[str, str, str], float] | None = None,
) -> float:
    """Learned prior: which moods work for this key? Unseen → 0.5."""
    if audio_key is None or pattern_lookup is None:
        return 0.5
    return pattern_lookup("key", audio_key, clip_mood)


def tension_fit(audio_tension: float | None, clip_role: str) -> float:
    """High tension (>0.7) favours hero/action; low tension (<0.3) favours
    detail/ambient/establishing. Medium → neutral."""
    if audio_tension is None:
        return 0.5
    if audio_tension > 0.7:
        return 1.0 if clip_role in {"hero", "action"} else 0.2
    if audio_tension < 0.3:
        return 1.0 if clip_role in {"detail", "ambient", "establishing"} else 0.4
    return 0.5


def energy_match(audio_energy: float | None, motion_score: float | None) -> float:
    """Close match between audio energy and clip motion → high score."""
    if audio_energy is None or motion_score is None:
        return 0.5
    return 1.0 - abs(audio_energy - motion_score)


def spectral_fit(
    spectral_hash: str | None,
    clip: ClipFeatures,
    pattern_lookup: Callable[[str, str, int], float] | None = None,
) -> float:
    """Learned prior keyed on (spectral-hash bucket, style-bucket). Unseen → 0.5."""
    if spectral_hash is None or pattern_lookup is None:
        return 0.5
    return pattern_lookup("spectral", spectral_hash, clip.style_bucket_id)


def groove_fit(audio_groove: str | None, motion_score: float | None) -> float:
    """Placeholder: high-groove rhythm (four-on-the-floor etc.) aligns with medium motion.
    The real implementation would need a groove-template → expected motion-range
    mapping; for now return 0.5 when either is missing, 1.0 when motion in [0.3, 0.7]
    for any defined groove, 0.4 otherwise."""
    if audio_groove is None or motion_score is None:
        return 0.5
    return 1.0 if 0.3 <= motion_score <= 0.7 else 0.4


def historical_accept_rate(
    context_fingerprint: tuple[str | None, ...],
    clip: ClipFeatures,
    pattern_lookup: (
        Callable[[tuple[str | None, ...], int], tuple[int, int]] | None
    ) = None,
) -> float:
    """Wilson-lower-bound confidence that this clip is accepted in this context.
    0/0 → 0.5 (neutral, per release-gate rule).

    B-159: Memory-Lookups sind auf scene_id keyed (mem_decision.scene_id ist
    Truth, PatternAggregator schreibt target_ref={"scene_id": ...}). Wenn wir
    hier die VideoClip-id durchreichen, matcht der Lookup nie und das gesamte
    Lern-Loop ist tot.
    """
    if pattern_lookup is None:
        return 0.5
    accepts, total = pattern_lookup(context_fingerprint, clip.scene_id)
    return wilson_lower_bound(accepts, total)


def collision_penalty(predecessor: ClipFeatures | None, clip: ClipFeatures) -> float:
    """Penalty when the predecessor's embedding is far from this clip's.
    Returns a magnitude in [0, 1] — 0 means no collision, 1 means maximum.
    Low style_compat → high collision_penalty."""
    if predecessor is None:
        return 0.0
    sim = style_compat(predecessor, clip)
    # sim ∈ [-1, 1]; penalty peaks when sim is very low.
    # map: sim 0.6+ → penalty 0; sim 0.0 → penalty 0.6; sim -1 → penalty 1.0
    return max(0.0, 0.6 - sim)


def staleness_penalty(
    clip: ClipFeatures,
    window_recent_clip_ids: Sequence[int],
) -> float:
    """Penalty when the same clip was used very recently (within the last
    K cuts). Independent from the VariationsBudget (which is a hard gate) —
    this is a soft score penalty that kicks in slightly before the budget."""
    if clip.clip_id in window_recent_clip_ids:
        return 1.0
    return 0.0


# ── Main PacingScorer class ─────────────────────────────────────────────────


# The 13 canonical term keys (without w_ prefix). Frozen set for validation.
CANONICAL_TERM_KEYS: frozenset[str] = frozenset(
    {
        "role",
        "style",
        "mood_video",
        "mood_audio",
        "genre",
        "key",
        "tension",
        "energy",
        "spectral",
        "groove",
        "memory",
        "collision",
        "freshness",
    }
)

# The default weights per Design §6.5. Must sum to something non-zero per
# convention; they need NOT sum to 1.0 — the total_score is NOT normalized
# by weight sum (the previous failed attempt did that incorrectly).
DEFAULT_WEIGHTS: dict[str, float] = {
    "w_role": 0.25,
    "w_style": 0.15,
    "w_mood_video": 0.10,
    "w_mood_audio": 0.10,
    "w_genre": 0.15,
    "w_key": 0.10,
    "w_tension": 0.08,
    "w_energy": 0.15,
    "w_spectral": 0.05,
    "w_groove": 0.07,
    "w_memory": 0.20,
    "w_collision": 0.10,  # penalty
    "w_freshness": 0.05,  # penalty
}


class PacingScorer:
    def __init__(
        self,
        weights: Mapping[str, float] | None = None,
        weights_profile: str | None = None,
        pattern_lookup: Callable[..., Any] | None = None,
    ) -> None:
        """Args:
            weights: full or partial override map of weight names (`w_role`, `w_style`, ...).
                    Keys must match DEFAULT_WEIGHTS exactly. Unknown keys → ValueError.
            weights_profile: optional string name of a YAML profile in
                    `config/pacing_weights/<name>.yaml`. If supplied, the YAML is
                    loaded and merged on top of DEFAULT_WEIGHTS; any explicit
                    `weights` argument further overrides. If the YAML file does
                    not exist, `weights_profile` silently falls back to defaults
                    (so tests can reference "default" without requiring the
                    file to exist yet — T6.3 writes the YAMLs).
            pattern_lookup: callable(kind, *keys) → value, used by genre_prior,
                    key_prior, spectral_fit, historical_accept_rate. If None,
                    those terms return 0.5 (Wilson-neutral).

        Raises:
            ValueError: if `weights` has unknown keys.
        """
        self._weights = self._resolve_weights(weights, weights_profile)
        self._pattern_lookup = pattern_lookup

    @staticmethod
    def _resolve_weights(
        weights: Mapping[str, float] | None,
        weights_profile: str | None,
    ) -> dict[str, float]:
        resolved = dict(DEFAULT_WEIGHTS)
        if weights_profile is not None:
            profile_path = Path("config/pacing_weights") / f"{weights_profile}.yaml"
            if profile_path.exists():
                try:
                    data = (
                        yaml.safe_load(profile_path.read_text(encoding="utf-8")) or {}
                    )
                    for k, v in data.items():
                        if k in DEFAULT_WEIGHTS:
                            resolved[k] = float(v)
                        else:
                            # Unknown keys in YAML are ignored (future-proofing;
                            # but an explicit `weights` arg with an unknown key
                            # is rejected below).
                            pass
                except (yaml.YAMLError, ValueError, OSError):
                    # Malformed YAML → fall back to defaults silently.
                    pass
        if weights is not None:
            unknown = set(weights.keys()) - set(DEFAULT_WEIGHTS.keys())
            if unknown:
                raise ValueError(
                    f"Unknown weight keys: {sorted(unknown)}. "
                    f"Expected one of {sorted(DEFAULT_WEIGHTS.keys())}."
                )
            for k, v in weights.items():
                resolved[k] = float(v)
        return resolved

    def score(
        self,
        clip: ClipFeatures,
        ctx: AudioContext,
        predecessor: ClipFeatures | None = None,
        recent_clip_ids: Sequence[int] | None = None,
    ) -> tuple[float, dict[str, float]]:
        """Compute the 13-term weighted sum for a single candidate clip.

        Returns:
            (total, contribs) where `contribs[term_key]` is the signed contribution
            of that term to the total (weight × raw_score for positive terms,
            -(weight × magnitude) for penalties). `sum(contribs.values()) == total`
            within FP tolerance.
        """
        recent = list(recent_clip_ids) if recent_clip_ids is not None else []
        fingerprint: tuple[str | None, ...] = (
            ctx.at_genre,
            ctx.at_section_type,
            f"{ctx.at_bpm:.0f}" if ctx.at_bpm is not None else None,
        )

        # B-217 perf: style_compat einmal berechnen, fuer collision_penalty
        # wiederverwenden. Vorher rief collision_penalty intern style_compat
        # nochmal auf -> doppelte cosine-Similarity-Computation pro score().
        # Ueber 500-Pool-Pass kostet das ~10ms unnoetig.
        style_sim = style_compat(predecessor, clip)
        collision_mag = (
            max(0.0, 0.6 - style_sim) if predecessor is not None else 0.0
        )

        raw: dict[str, float] = {
            "role": role_fit(ctx.at_section_type, clip.role),
            "style": style_sim,
            "mood_video": mood_match(ctx.at_mood_video, clip.mood_refined),
            "mood_audio": mood_match(ctx.at_mood_audio, clip.mood_refined),
            "genre": genre_prior(
                ctx.at_genre, clip.style_bucket_id, self._pattern_lookup
            ),
            "key": key_prior(ctx.at_key, clip.mood_refined, self._pattern_lookup),
            "tension": tension_fit(ctx.at_harmonic_tension, clip.role),
            "energy": energy_match(ctx.at_energy, clip.motion_score),
            "spectral": spectral_fit(ctx.at_spectral_hash, clip, self._pattern_lookup),
            "groove": groove_fit(ctx.at_groove_template, clip.motion_score),
            "memory": historical_accept_rate(fingerprint, clip, self._pattern_lookup),
            "collision": collision_mag,
            "freshness": staleness_penalty(clip, recent),
        }

        # Penalty terms are subtracted — we negate the weighted contribution
        # so contribs.values().sum() equals total.
        POSITIVE = {
            "role",
            "style",
            "mood_video",
            "mood_audio",
            "genre",
            "key",
            "tension",
            "energy",
            "spectral",
            "groove",
            "memory",
        }
        PENALTY = {"collision", "freshness"}

        contribs: dict[str, float] = {}
        for key in POSITIVE:
            w = self._weights[f"w_{key}"]
            contribs[key] = w * raw[key]
        for key in PENALTY:
            w = self._weights[f"w_{key}"]
            contribs[key] = -(w * raw[key])

        total = sum(contribs.values())
        # Scorer does NOT clip to [0, 1] — test_negative_score_allowed verifies this.
        return float(total), contribs

    def score_batch(
        self,
        clips: Sequence[ClipFeatures],
        ctx: AudioContext,
        predecessor: ClipFeatures | None = None,
        recent_clip_ids: Sequence[int] | None = None,
    ) -> list[tuple[float, dict[str, float]]]:
        """Vectorized over clips.

        For now: loop + call `score()`. The name preserves the future
        optimization path (NumPy broadcasting) once the scoring helpers
        are rewritten vector-first. Behaviour is currently a pure fan-out
        — test_batch_score_matches_single verifies equivalence.
        """
        return [self.score(c, ctx, predecessor, recent_clip_ids) for c in clips]
