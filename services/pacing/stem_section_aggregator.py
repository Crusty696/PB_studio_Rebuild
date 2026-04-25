"""Foundation Slice 0 / FR-S0-3: Stem-Energy aggregation per macro-section.

Maps Demucs 4-stem output × structure-detected sections to a per-section
dict of stem energies. Used by:
- Slice 1 A.4 (Vocal-on-Hold) — query vocal-energy of current section
- Slice 2 B (Stem→Shot-Type) — pick dominant stem per section
- Slice 3 D.1 (Audio-Mood-Vector) — feed stem-distribution into mood-vec
"""
from __future__ import annotations

from typing import Iterable, Mapping

import numpy as np

EPS = 1e-9
DEFAULT_STEM_NAMES = ("vocals", "drums", "bass", "other")


def _rms(arr: np.ndarray) -> float:
    if arr.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(arr.astype(np.float64) ** 2)))


def aggregate(
    stems: Mapping[str, np.ndarray],
    sections: Iterable[object],
    sr: int,
) -> dict:
    """Per-section stem-energy dictionary.

    Args:
        stems: dict like {"vocals": np.ndarray(samples,), "drums": ..., "bass": ..., "other": ...}.
            Each array is mono float, sample-rate-aligned. Multi-channel is reduced to mean.
        sections: iterable of section-objects with attrs `id` (or index), `start_time`, `end_time`.
        sr: sample-rate.

    Returns:
        dict[section_id, dict[stem_name, float]]. Energies are L1-normalized
        within each section so they sum to 1 (relative dominance), making them
        directly comparable across sections of different absolute loudness.
    """
    # Reduce multi-channel
    norm_stems = {}
    for name, arr in stems.items():
        if arr.ndim > 1:
            arr = arr.mean(axis=arr.ndim - 1) if arr.shape[-1] <= 8 else arr.mean(axis=0)
        norm_stems[name] = arr.astype(np.float32, copy=False)

    out: dict = {}
    for i, section in enumerate(sections):
        sect_id = getattr(section, "id", None)
        if sect_id is None:
            sect_id = getattr(section, "index", i)
        start = float(getattr(section, "start_time", 0.0))
        end = float(getattr(section, "end_time", 0.0))
        i0 = max(0, int(start * sr))
        i1 = max(i0, int(end * sr))

        per_stem = {}
        for name, samples in norm_stems.items():
            i1_clamped = min(i1, len(samples))
            if i1_clamped <= i0:
                per_stem[name] = 0.0
            else:
                per_stem[name] = _rms(samples[i0:i1_clamped])

        total = sum(per_stem.values())
        if total > EPS:
            per_stem = {k: v / total for k, v in per_stem.items()}

        out[sect_id] = per_stem

    return out


def dominant_stem(per_section_energies: Mapping[str, float], threshold: float = 0.35) -> str | None:
    """Return the stem name whose relative energy ≥ threshold AND is max.

    Returns None if no stem dominates clearly.
    """
    if not per_section_energies:
        return None
    name, val = max(per_section_energies.items(), key=lambda kv: kv[1])
    if val >= threshold:
        return name
    return None
