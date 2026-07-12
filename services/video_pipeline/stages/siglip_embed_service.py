"""SigLIP-Vision-Embed-Service.

Plan: VIDEO-PIPELINE-ENGINE-2026-05-19
Phase: 31 (Tier 3 Workspace+Services)

Lazy-loaded SigLIP-Modell. Default ``google/siglip-so400m-patch14-384`` (1152-dim).
"""
from __future__ import annotations

import numpy as np

from services.model_warmup import SIGLIP_DEFAULT_MODEL


__all__ = ["SigLipEmbedService"]


class SigLipEmbedService:
    def __init__(
        self,
        *,
        model_id: str = SIGLIP_DEFAULT_MODEL,
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
        """Holt das SigLIP-Modell vom zentralen ModelManager (Befund 2).

        Root-Cause-Fix statt eigenem ``from_pretrained``: ModelManager haelt
        genau EINE ``so400m``-Instanz (Single-VRAM-Model-Invariante) und
        serialisiert das Laden ueber ``GPU_LOAD_LOCK``. Vorher lud die Pipeline
        ein ZWEITES so400m neben dem ModelManager-Modell (Enrichment/VectorDB)
        -> zwei ~2.5-3.5 GB Modelle auf 6 GB -> OOM. Gleiches Modell -> identische
        1152-dim Embeddings, kein Qualitaetsverlust; fp16 ist konsistent mit den
        bereits gespeicherten App-Embeddings.

        ModelManager cached intern (Cache-Hit), daher ist wiederholtes ``load()``
        billig und liefert stets das AKTUELLE Modell (kein veralteter Ref nach
        einem Modell-Swap) — vorausgesetzt der Aufrufer haelt waehrend der
        Inferenz den ``gpu_serializer`` (siehe SigLipEmbedStage).
        """
        from services.model_manager import ModelManager
        self._model, self._processor = ModelManager().load_siglip(self.model_id)

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
        # Inputs auf Device UND dtype des Modells bringen. ModelManager laedt
        # SigLIP in fp16 (HalfTensor); fp32-pixel_values gegen fp16-Weights
        # wirft "Input type ... and weight type ... should be the same". Nur
        # Float-Tensoren casten — Integer-Tensoren (falls vorhanden) nur moven.
        p0 = next(self._model.parameters())
        model_device, model_dtype = p0.device, p0.dtype
        moved = {}
        for k, v in inputs.items():
            if torch.is_floating_point(v):
                moved[k] = v.to(device=model_device, dtype=model_dtype)
            else:
                moved[k] = v.to(model_device)
        inputs = moved
        with torch.no_grad():
            features = self._model.get_image_features(**inputs)
        arr = features.detach().cpu().float().numpy()
        if self.dtype == "float16":
            arr = arr.astype(np.float16)
        return arr

    def unload(self) -> None:
        """Gibt lokale Referenzen und das passende ModelManager-SigLIP frei.

        B-333: Die Video-Pipeline ruft Stage-``unload()`` nach jedem GPU-Stage
        auf, damit SigLIP vor RAFT wieder VRAM freigibt. Der ModelManager wird
        nur entladen, wenn sein Hauptslot exakt dieses SigLIP haelt; andere
        aktuell geladene Hauptmodelle bleiben unberuehrt.
        """
        if self._model is None and self._processor is None:
            return

        self._model = None
        self._processor = None
        from services.model_manager import ModelManager

        manager = ModelManager()
        if (
            getattr(manager, "current_model_id", None) == self.model_id
            and getattr(manager, "model_type", None) == "siglip"
        ):
            manager.unload()
