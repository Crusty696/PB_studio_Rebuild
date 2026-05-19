"""Scene-Detect-Primitive (PySceneDetect-Wrapper).

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 13 (Tier 2 Building-Blocks)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from scenedetect import detect, ContentDetector, open_video  # type: ignore[import]


__all__ = ["Scene", "detect_scenes"]


@dataclass(frozen=True)
class Scene:
    start_s: float
    end_s: float
    index: int

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


def detect_scenes(path: Path, *, threshold: float = 27.0) -> list[Scene]:
    """Erkennt Szenen-Cuts via PySceneDetect ContentDetector.

    Args:
        path: Video-Datei.
        threshold: ContentDetector-Schwelle. Niedriger = sensitiver.

    Returns:
        Liste von Scene-Objekten mit (start_s, end_s, index).
        Mind. 1 Eintrag (das ganze Video als 1 Scene falls kein Cut gefunden).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"video not found: {path}")

    scene_list = detect(str(path), ContentDetector(threshold=threshold))

    if not scene_list:
        vid = open_video(str(path))
        duration = vid.duration.seconds
        return [Scene(start_s=0.0, end_s=duration, index=0)]

    out: list[Scene] = []
    for idx, (start, end) in enumerate(scene_list):
        out.append(Scene(
            start_s=start.seconds,
            end_s=end.seconds,
            index=idx,
        ))
    return out
