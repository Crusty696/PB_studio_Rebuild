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
        #
        # B-502: Der eigentliche Load (inkl. ~1 GB fp32 VRAM-Alloc) lief bisher
        # komplett am ModelManager-Locking vorbei — parallele Loads anderer
        # Threads (Demucs/beat_this/SigLIP unter GPU_LOAD_LOCK) konnten
        # gleichzeitig allozieren → OOM-Race auf der 6-GB GTX 1060. Fix:
        # Load unter GPU_LOAD_LOCK + proaktiver VRAM-Precheck via
        # ModelManager._handle_oom_prevention (F-011-Pattern).
        # Lock-Ordnung bleibt konsistent: RaftMotionStage haelt beim Aufruf
        # bereits den gpu_serializer (= legacy GPU_EXECUTION_LOCK), danach
        # GPU_LOAD_LOCK — exakt die gpu_resource_lease-Reihenfolge
        # (EXECUTION → LOAD, model_manager.py).
        from services.model_manager import GPU_LOAD_LOCK, ModelManager
        with GPU_LOAD_LOCK:
            if self.is_loaded:  # double-check nach Lock-Wartezeit
                return
            use_cuda = self.device.startswith("cuda") and torch.cuda.is_available()
            if use_cuda:
                # Precheck kann bei knappem Speicher das ModelManager-Hauptmodell
                # entladen bzw. RuntimeError werfen (statt spaeter hartem CUDA-OOM).
                ModelManager()._handle_oom_prevention(
                    f"RAFT '{self.variant}' laden (RaftMotionService)"
                )
            if self.variant == "raft_large":
                model = raft_large(weights=Raft_Large_Weights.C_T_SKHT_V2)
            else:
                model = raft_small(weights=Raft_Small_Weights.C_T_V2)
            if use_cuda:
                model = model.to(self.device)
            self._model = model.float().eval()

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

        model_dtype = next(self._model.parameters(), a).dtype
        if a.dtype != model_dtype:
            a = a.to(dtype=model_dtype)
            b = b.to(dtype=model_dtype)

        # B-440: torchvision-RAFT verlangt H,W teilbar durch 8. Keyframe- bzw.
        # interpolierte Dims sind das nicht garantiert -> auf Vielfaches von 8
        # padden (replicate) und den Flow danach auf Originalgroesse zurueck-
        # schneiden. Ohne Guard: ValueError "feature encoder should downsample
        # H and W by 8".
        import torch.nn.functional as F
        _, _, h, w = a.shape
        pad_h = (8 - h % 8) % 8
        pad_w = (8 - w % 8) % 8
        if pad_h or pad_w:
            a = F.pad(a, (0, pad_w, 0, pad_h), mode="replicate")
            b = F.pad(b, (0, pad_w, 0, pad_h), mode="replicate")

        old_default_dtype = torch.get_default_dtype()
        try:
            torch.set_default_dtype(torch.float32)
            with torch.no_grad():
                flows = self._model(a, b, num_flow_updates=self.iter_count)
        finally:
            torch.set_default_dtype(old_default_dtype)
        flow = flows[-1][0]  # [2, H, W]
        if pad_h or pad_w:
            flow = flow[:, :h, :w]
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
