"""B-440 Regression — RAFT compute_flow paddet H/W auf Vielfache von 8.

Deterministisch (CPU, Spy-Modell statt echtem RAFT-Download). Vor dem Fix
crashte torchvision-RAFT mit "feature encoder should downsample H and W by 8"
auf Frame-Groessen, die nicht durch 8 teilbar sind (reale Videos / scale != 1.0).
"""
from __future__ import annotations

import numpy as np
import torch


class _DimSpyRaft(torch.nn.Module):
    """Faelscht RAFT: merkt sich die Input-H/W und liefert Null-Flow zurueck."""

    def __init__(self):
        super().__init__()
        self.seen: list[tuple[int, int]] = []

    def forward(self, a, b, num_flow_updates=12):
        self.seen.append((a.shape[-2], a.shape[-1]))
        flow = torch.zeros((1, 2, a.shape[-2], a.shape[-1]), dtype=a.dtype, device=a.device)
        return [flow]


def _make_service(scale: float):
    from services.video_pipeline.stages.raft_motion_service import RaftMotionService

    svc = RaftMotionService(variant="raft_large", iter_count=4, resolution_scale=scale)
    svc.device = "cpu"          # kein CUDA noetig
    svc._model = _DimSpyRaft().eval()   # is_loaded -> load() ist No-Op
    return svc


def test_b440_non_divisible_dims_padded_to_multiple_of_8():
    svc = _make_service(1.0)
    h, w = 158, 238  # beide nicht durch 8 teilbar
    f1 = np.zeros((h, w, 3), dtype=np.uint8)
    f2 = np.ones((h, w, 3), dtype=np.uint8)

    flow = svc.compute_flow(f1, f2)

    seen_h, seen_w = svc._model.seen[-1]
    assert seen_h % 8 == 0 and seen_w % 8 == 0, (
        f"RAFT-Input nicht auf /8 gepadded: {seen_h}x{seen_w}"
    )
    # Flow wird auf Originalgroesse zurueckgeschnitten
    assert flow.shape == (h, w, 2)


def test_b440_scale_then_pad_to_8():
    svc = _make_service(0.5)
    h, w = 200, 300  # *0.5 -> 100x150 (100%8=4, 150%8=6) -> Pad noetig
    f1 = np.zeros((h, w, 3), dtype=np.uint8)
    f2 = np.ones((h, w, 3), dtype=np.uint8)

    flow = svc.compute_flow(f1, f2)

    seen_h, seen_w = svc._model.seen[-1]
    assert seen_h % 8 == 0 and seen_w % 8 == 0
    # Ausgabe auf die interpolierte (pre-pad) Groesse zurueckgeschnitten
    assert flow.shape == (100, 150, 2)


def test_b440_already_divisible_no_change():
    svc = _make_service(1.0)
    h, w = 160, 240  # bereits /8
    f1 = np.zeros((h, w, 3), dtype=np.uint8)
    f2 = np.ones((h, w, 3), dtype=np.uint8)

    flow = svc.compute_flow(f1, f2)

    seen_h, seen_w = svc._model.seen[-1]
    assert (seen_h, seen_w) == (160, 240)  # kein Pad
    assert flow.shape == (h, w, 2)
