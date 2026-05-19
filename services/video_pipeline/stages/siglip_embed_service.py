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
    ):
        self.model_id = model_id
        self.device = device
        self.dtype = dtype
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
