# 18 — GPU-Lock-Awareness (read-only pynvml)

> Plan: `VIDEO-PIPELINE-ENGINE-2026-05-19` — Tier 2
> Status: planned · 2026-05-19

## Ziel

GPU-Heavy Stages (SigLIP, RAFT, Proxy-NVENC) respektieren Audio-V2 `GPU_EXECUTION_LOCK` ohne ihn anzufassen.

## Strategie

- Vor GPU-Aufruf: pynvml `nvmlDeviceGetMemoryInfo` → vram_free_gb pruefen.
- Wenn vram_free_gb < required + 0.5 GB safety → kurz warten (2 s polling, max 60 s) oder Stage `partial`.
- Pro Stage required-VRAM dokumentiert:
  - SigLIP-So400m: ~1.5 GB
  - RAFT: ~1.5 GB
  - NVENC Proxy: ~0.5 GB
- Keine eigene Lock-Datei, keine eigene Mutex — read-only Awareness.

## Coexistenz-Matrix

| V2 aktiv | Brain V3 aktiv | LLM-Plan-B aktiv | Plan A erlaubt |
|---|---|---|---|
| ja | nein | nein | warten (VRAM voll) |
| nein | ja | nein | warten oder partial |
| nein | nein | ja (Reasoner ~5 GB) | warten |
| nein | nein | LLM-Embed CPU-only | ok |
| alle aus | - | - | ok |

## Verifikation

- Mit laufendem Demucs (V2 holdt Lock): SigLIP-Stage wartet, kein Crash
- Nach V2-Done: Stage laeuft weiter
- `pytest tests/test_services/test_gpu_lock_aware.py -v` gruen
