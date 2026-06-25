# 31 — SigLIP-Vision-Embed-Service

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Tier 3
> Status: planned · 2026-05-19

## Ziel

Pro Keyframe ein Embedding. Brain-V3-Coexistenz.

## Scope

```python
class SigLipEmbedService:
    def __init__(self, model_id: str = "siglip-so400m-patch14-384"): ...
    def embed_batch(self, frames: list[np.ndarray]) -> np.ndarray:  # [N, dim]
        # GPU-Lock-Aware: vor Run pynvml-Probe
        # Batch 8 frames default (1060 6GB)
        ...
```

- Output: `embeddings.npy` in `storage/video_analysis/<track_id>/`
- Format: `np.float16` (halb so gross wie f32, kein Quality-Verlust fuer Cosine).
- Resume: nach jedem Batch in checkpoint.json `completed_frames += batch_size`.

## Brain-V3-Coexistenz

- Brain V3 nutzt eigene SigLIP-Instanz fuer eigenen Zweck.
- Plan A laedt eigenes SigLIP-Modell, kein Singleton-Share (Hartregel D-032 separate dev-brain).
- VRAM-Konflikt: Read-Only-Probe vermeidet OOM.

## Verifikation

- Embedding-Dim korrekt (1152 fuer so400m)
- Cosine-Aehnlichkeit zwischen Frame-Variationen plausibel
- `pytest tests/test_services/test_siglip_embed.py -v` gruen
