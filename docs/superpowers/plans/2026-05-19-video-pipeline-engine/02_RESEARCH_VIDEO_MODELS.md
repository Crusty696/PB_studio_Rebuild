# 02 — Recherche Video-Modelle (Quality + Lizenz)

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Tier 1
> Status: planned · 2026-05-19 · Recherche-Step

## Best-per-Task-Modelle (zu verifizieren)

### Scene-Detect
- **PySceneDetect** (BSD-3) — etabliert, Python-only, fast.
- Alternativ: TransNetV2 (CC-BY-NC — **raus**).

### Keyframe-Extraction
- I-Frame-Extract via ffmpeg (LGPL/GPL).
- Mid-Scene-Frame als Standard-Heuristik.

### Vision-Embeddings
- **SigLIP** (Apache 2.0) — bestaetigt fuer PB Studio (D-008).
- SigLIP-So400m (best quality, ~600 MB VRAM).

### Motion-Flow
- **RAFT** (BSD-3) — implementiert in `torchvision.models.optical_flow`.
- Klein, GPU-effizient, gut auf GTX 1060.

### VLM-Captioning
- Modelle kommen aus Plan B Registry.
- Empfehlung sparse (nur Scene-Keyframes): minicpm-v 8B, llava-phi3, moondream.

## Pflicht-Pruefung vor Implementation

- Lizenz pro Modell verifizieren
- VRAM-Realismus auf 1060 messen
- PySceneDetect-Version (>= 0.6.x) testen
- RAFT auf 1060 mit 1080p-Frames benchmarken

## Offene Klaerungs-Punkte

- [ ] SigLIP-Variant (Base / So400m) Default — Quality vs Speed
- [ ] PySceneDetect threshold tunable per Quality-Profile?
- [ ] Audio-Demuxing fuer Cross-Modal: nutzt V2 Audio-Outputs (Pfad zu V2-Stems / V2-DB) ohne Doppel-Decode
