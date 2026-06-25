# 32 — RAFT-Motion-Service

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Tier 3
> Status: planned · 2026-05-19

## Ziel

Optical-Flow pro Frame-Paar. Output: motion_magnitude, motion_direction.

## Scope

```python
class RaftMotionService:
    def __init__(self, model_variant: str = "raft_large"): ...
    def compute_flow(self, frame_a: np.ndarray, frame_b: np.ndarray) -> np.ndarray:  # [H, W, 2]
        # GPU-Lock-Aware
        ...
    def aggregate(self, flow: np.ndarray) -> MotionStats:
        # mean magnitude, dominant direction, std
        ...
```

- Frame-Pairs nach Sample-Pattern (z. B. alle 2 s zwischen consecutive Sample-Frames).
- Output: `motion.json` mit `[time_s, magnitude, direction, std]`-Liste.
- Quality-Profile bestimmt Aufloesung (1080p / 720p / 480p).

## Verifikation

- Statisches Video → niedrige Magnitude
- Schnelles Pan → hohe Magnitude
- `pytest tests/test_services/test_raft_motion.py -v` gruen
