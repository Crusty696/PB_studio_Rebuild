# 72 — Long-Form 4 h Video

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Cross-Cutting
> Status: planned · 2026-05-19

## Ziel

4 h Video Vollstaendigkeit. Sparse-Sampling mit Coverage-Garantie.

## Strategie

- Scene-Detect: Stream-Mode (kein Full-Load).
- Keyframe-Extract: 1 Frame/2 s + Scene-Anchors → bei 4 h ~7200 + ~hundert Scenes = ~7300 JPEG (~360 MB).
- SigLIP-Embed: alle Keyframes (1152 × 7300 × 2 bytes = ~16 MB). Batched 8/16.
- RAFT-Motion: alle Consecutive-Sample-Pairs (~7200 Pairs). Aufloesung downscale Quality-Profile.
- VLM-Caption: nur Scene-Keyframes (Quality-Profile bestimmt Frequenz).
- Cross-Modal: liest V2-Audio-Outputs.

## Performance-Schaetzung GTX 1060 (Maximum-Quality, Verifikation Pflicht)

- Scene-Detect: ~5 min
- Keyframe-Extract: ~10 min (mit NVDEC)
- SigLIP: 7300 Frames @ 50 frames/s (Batch 16) = ~2.5 min
- RAFT: 7200 Pairs @ 5 pairs/s = ~24 min
- VLM (sparse, ~100 Captions × 3 s) = ~5 min
- Cross-Modal: ~1 min
- **Total ~45-60 min fuer 4 h Video** (Verifizierung Pflicht).

## Resume-Punkte

- Pro Chunk (5 min Video-Slice) Checkpoint.
- Bei Crash: weiter ab letzter abgeschlossener Slice.

## Verifikation

- Synthetisches 4 h Video durch alle Stages
- Coverage ≥ 99.5 %
- Resume nach mid-Pipeline-Kill funktioniert
