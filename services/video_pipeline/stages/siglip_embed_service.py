"""SigLIP-Vision-Embed-Service.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 31 (Tier 3 Workspace+Services)

Lazy-loaded SigLIP-Modell. Default ``google/siglip-so400m-patch14-384`` (1152-dim).
"""
from __future__ import annotations

import numpy as np


__all__ = ["SigLipEmbedService"]


class SigLipEmbedService:
    def __init__(
        self,
        *,
        model_id: str = "google/siglip-so400m-patch14-384",
        device: str = "cuda:0",
        dtype: str = "float16",  # storage dtype
        vram_required_gb: float = 3.5,  # so400m fp32 footprint estimate
    ):
        self.model_id = model_id
        self.device = device
        self.dtype = dtype
        self.vram_required_gb = vram_required_gb
        self._model = None
        self._processor = None

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        if self.is_loaded:
            return
        from transformers import AutoModel, AutoProcessor
        import torch
        self._processor = AutoProcessor.from_pretrained(self.model_id)
        model = AutoModel.from_pretrained(self.model_id)
        if self.device.startswith("cuda") and torch.cuda.is_available():
            # F-2: respect Audio-V2 GPU_EXECUTION_LOCK indirectly via free-VRAM
            # probe so we do not allocate on top of a busy GTX 1060 (6 GB).
            from services.video_pipeline.primitives.gpu_lock_aware import wait_for_vram
            dev_idx = int(self.device.split(":")[-1]) if ":" in self.device else 0
            wait_for_vram(self.vram_required_gb, device=dev_idx)
            model = model.to(self.device)
        self._model = model.eval()

    def embed_batch(self, frames: list[np.ndarray]) -> np.ndarray:
        """Liefert ``np.ndarray`` shape ``(N, embed_dim)`` ``float16`` als Default.

        Args:
            frames: Liste von RGB-uint8-Arrays ``(H, W, 3)``.
        """
        self.load()
        from PIL import Image
        import torch
        imgs = [Image.fromarray(f) for f in frames]
        inputs = self._processor(images=imgs, return_tensors="pt")
        if self.device.startswith("cuda") and torch.cuda.is_available():
            inputs = {k: v.to(self.device) for k, v in inputs.items()}
        with torch.no_grad():
            features = self._model.get_image_features(**inputs)
        arr = features.detach().cpu().float().numpy()
        if self.dtype == "float16":
            arr = arr.astype(np.float16)
        return arr

    def unload(self) -> None:
        self._model = None
        self._processor = None
        try:
            import torch
            torch.cuda.empty_cache()
        except Exception:
            pass
