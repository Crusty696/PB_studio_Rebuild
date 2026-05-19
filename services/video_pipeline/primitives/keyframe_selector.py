"""Keyframe-Selector.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 14 (Tier 2 Building-Blocks)

Liefert pro Szene N Keyframe-Timestamps + Rolle. Aufruf-Beispiele:

- ``mode="mid"``           — 1 Frame Mitte pro Szene
- ``mode="anchors_3"``     — Anfang / Mitte / Ende pro Szene
- ``uniform_every_s``      — zusaetzliche Anker alle X s ueber gesamtes Video
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence


__all__ = ["Keyframe", "select_keyframes"]


@dataclass(frozen=True)
class Keyframe:
    scene_idx: int
    time_s: float
    role: str   # "start" | "mid" | "end" | "uniform"


def _scene_anchors(sc, mode: str, idx: int) -> list[Keyframe]:
    if mode == "mid":
        return [Keyframe(scene_idx=idx, time_s=(sc.start_s + sc.end_s) / 2.0, role="mid")]
    if mode == "anchors_3":
        start = sc.start_s
        end = max(sc.start_s, sc.end_s - 0.001)
        mid = (sc.start_s + sc.end_s) / 2.0
        return [
            Keyframe(scene_idx=idx, time_s=start, role="start"),
            Keyframe(scene_idx=idx, time_s=mid, role="mid"),
            Keyframe(scene_idx=idx, time_s=end, role="end"),
        ]
    raise ValueError(f"unknown mode: {mode!r}")


def select_keyframes(
    scenes: Sequence,
    *,
    mode: str = "anchors_3",
    uniform_every_s: float | None = None,
) -> list[Keyframe]:
    """Liefert sortierte Keyframes pro Szene + optional uniform-Anker.

    Args:
        scenes: Liste von Scene-Objekten (start_s, end_s, index).
        mode: ``mid`` oder ``anchors_3``.
        uniform_every_s: Falls gesetzt, zusaetzliche Anker alle X s ueber Gesamt-Duration.
    """
    if mode not in {"mid", "anchors_3"}:
        raise ValueError(f"unknown mode: {mode!r}")

    if not scenes:
        return []

    out: list[Keyframe] = []
    for sc in scenes:
        out.extend(_scene_anchors(sc, mode, sc.index))

    if uniform_every_s is not None and uniform_every_s > 0:
        duration = max(sc.end_s for sc in scenes)
        t = 0.0
        existing_times = {round(k.time_s, 4) for k in out}
        while t < duration:
            rounded = round(t, 4)
            if rounded not in existing_times:
                # Finde welche Szene t beinhaltet (fuer scene_idx)
                idx = next((sc.index for sc in scenes if sc.start_s <= t < sc.end_s),
                          scenes[-1].index)
                out.append(Keyframe(scene_idx=idx, time_s=t, role="uniform"))
                existing_times.add(rounded)
            t += uniform_every_s

    return sorted(out, key=lambda k: (k.time_s, k.role))
