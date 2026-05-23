"""RAFT-Motion-Service.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 32 (Tier 3 Workspace+Services)
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


__all__ = ["RaftMotionService", "MotionStats"]


@dataclass(frozen=True)
class MotionStats:
    mean_magnitude: float
    std_magnitude: float
    dominant_direction_rad: float


class RaftMotionService:
    def __init__(
        self,
        *,
        variant: str = "raft_large",   # "raft_large" | "raft_small"
        device: str = "cuda:0",
        iter_count: int = 12,
        resolution_scale: float = 1.0,
    ):
        if variant not in {"raft_large", "raft_small"}:
            raise ValueError(f"unknown variant: {variant!r}")
        self.variant = variant
        self.device = device
        self.iter_count = iter_count
        self.resolution_scale = resolution_scale
        self._model = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        if self.is_loaded:
            return
        import torch
        from torchvision.models.optical_flow import raft_large, raft_small
        from torchvision.models.optical_flow import (
            Raft_Large_Weights, Raft_Small_Weights,
        )
        # Befund 2: RAFT bleibt bewusst raft_large. ModelManager.load_raft laedt
        # nur raft_small — das waere ein Optical-Flow-Qualitaetsverlust. Die
        # Execution-Koordination uebernimmt der gpu_serializer in RaftMotionStage;
        # raft_large (~1 GB) koexistiert problemlos mit dem so400m im VRAM-Budget.
        if self.variant == "raft_large":
            model = raft_large(weights=Raft_Large_Weights.C_T_SKHT_V2)
        else:
            model = raft_small(weights=Raft_Small_Weights.C_T_V2)
        if self.device.startswith("cuda") and torch.cuda.is_available():
            model = model.to(self.device)
        self._model = model.eval()

    def compute_flow(self, frame_a: np.ndarray, frame_b: np.ndarray) -> np.ndarray:
        """Berechnet Optical-Flow zwischen ``frame_a`` und ``frame_b``.

        Args:
            frame_a, frame_b: RGB-uint8-Arrays ``(H, W, 3)``.

        Returns:
            ``np.ndarray`` shape ``(H, W, 2)`` (dx, dy) als float32.
        """
        self.load()
        import torch
        # CHW float [-1,1] (RAFT-Convention)
        def _to_tensor(arr: np.ndarray) -> "torch.Tensor":
            t = torch.from_numpy(arr).permute(2, 0, 1).float() / 127.5 - 1.0
            return t.unsqueeze(0)

        a = _to_tensor(frame_a)
        b = _to_tensor(frame_b)
        if self.device.startswith("cuda") and torch.cuda.is_available():
            a = a.to(self.device)
            b = b.to(self.device)
        if self.resolution_scale != 1.0:
            import torch.nn.functional as F
            scale = self.resolution_scale
            a = F.interpolate(a, scale_factor=scale, mode="bilinear", align_corners=False)
            b = F.interpolate(b, scale_factor=scale, mode="bilinear", align_corners=False)

        with torch.no_grad():
            flows = self._model(a, b, num_flow_updates=self.iter_count)
        flow = flows[-1][0]  # [2, H, W]
        return flow.detach().cpu().permute(1, 2, 0).float().numpy()

    @staticmethod
    def aggregate(flow: np.ndarray) -> MotionStats:
        dx = flow[..., 0]
        dy = flow[..., 1]
        mag = np.sqrt(dx ** 2 + dy ** 2)
        # Dominant direction = atan2 von mean dy/dx
        mean_dx = float(dx.mean())
        mean_dy = float(dy.mean())
        direction = float(np.arctan2(mean_dy, mean_dx))
        return MotionStats(
            mean_magnitude=float(mag.mean()),
            std_magnitude=float(mag.std()),
            dominant_direction_rad=direction,
        )

    def unload(self) -> None:
        self._model = None
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass
