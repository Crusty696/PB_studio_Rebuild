"""Frame-Sampler.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 12 (Tier 2 Building-Blocks)

Liefert Frame-Timestamps fuer Stages (SigLIP / RAFT / VLM).

Strategien:
- ``uniform(rate_s)`` — alle rate_s Sekunden ab 0
- ``scene_anchored(scenes, k=3)`` — k Anker pro Szene (start/mid/end fuer k=3)
- ``dense_until(n_max)`` — alle Frames bis Maximalanzahl
- ``mixed(rate_s, scenes, k)`` — Union aus uniform + scene_anchored, sortiert+unique
"""
from __future__ import annotations

from typing import Sequence


__all__ = ["sample_frame_times"]


def _uniform(duration_s: float, rate_s: float, fps: float) -> list[float]:
    if rate_s <= 0:
        raise ValueError("rate_s must be > 0")
    # B-573: Container-/Streamdauer kann bis in das Intervall nach dem letzten
    # decodierbaren Videoframe reichen (z.B. laengere Audiospur). Samplepunkte
    # innerhalb des letzten Frame-Intervalls vermeiden, sonst liefert FFmpeg
    # bei Langform-Medien am Ende 0 Bytes.
    frame_interval_s = 1.0 / fps if fps > 0 else 0.0
    sample_end_s = max(0.0, duration_s - frame_interval_s)
    times: list[float] = []
    t = 0.0
    while t < sample_end_s or not times:
        times.append(round(t, 6))
        t += rate_s
    return times


def _scene_anchored(scenes: Sequence[dict], k: int) -> list[float]:
    if k < 1:
        raise ValueError("k must be >= 1")
    out: list[float] = []
    for sc in scenes:
        s = float(sc["start_s"])
        e = float(sc["end_s"])
        if k == 1:
            out.append(round((s + e) / 2.0, 6))
        else:
            for i in range(k):
                # k Punkte: position = s + (e-s) * i/(k-1) wenn k>1
                # aber: end exklusiv -> letzten Anker leicht vor e
                if i == k - 1:
                    out.append(round(max(s, e - 0.001), 6))
                else:
                    out.append(round(s + (e - s) * i / (k - 1), 6))
    return out


def _dense_until(duration_s: float, fps: float, n_max: int) -> list[float]:
    step = 1.0 / fps if fps > 0 else 0.04
    times: list[float] = []
    t = 0.0
    while t < duration_s and len(times) < n_max:
        times.append(round(t, 6))
        t += step
    return times


def sample_frame_times(
    duration_s: float,
    fps: float,
    strategy: str,
    *,
    scenes: Sequence[dict] | None = None,
    rate_s: float | None = None,
    k: int = 3,
    n_max: int | None = None,
) -> list[float]:
    """Liefert sortierte Liste von Sample-Timestamps (Sekunden).

    Args:
        duration_s: Video-Laenge.
        fps: Frame-Rate (fuer dense_until).
        strategy: ``uniform`` / ``scene_anchored`` / ``dense_until`` / ``mixed``.
        scenes: Pflicht fuer ``scene_anchored`` und ``mixed``. List of
                dicts mit ``start_s`` und ``end_s``.
        rate_s: Pflicht fuer ``uniform`` und ``mixed``.
        k: Anzahl Anker pro Szene (Default 3).
        n_max: Pflicht fuer ``dense_until``.
    """
    if strategy == "uniform":
        if rate_s is None:
            raise ValueError("uniform requires rate_s")
        return _uniform(duration_s, rate_s, fps)

    if strategy == "scene_anchored":
        if not scenes:
            raise ValueError("scene_anchored requires scenes")
        return _scene_anchored(scenes, k)

    if strategy == "dense_until":
        if n_max is None:
            raise ValueError("dense_until requires n_max")
        return _dense_until(duration_s, fps, n_max)

    if strategy == "mixed":
        if rate_s is None or not scenes:
            raise ValueError("mixed requires rate_s and scenes")
        u = _uniform(duration_s, rate_s, fps)
        a = _scene_anchored(scenes, k)
        merged = sorted(set(u) | set(a))
        return merged

    raise ValueError(f"unknown strategy: {strategy!r}")
