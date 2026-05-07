# Brain V3 — Phase-0-Spike: GPU-Coexistenz

**Generiert:** 2026-05-03T12:00:15.458979  
**Skript:** `scripts/spike_brain_v3_gpu_coexistence.py`  
**Status:** code-fix-pending-live-verification — auf User-Hardware ausgefuehrt

## Umgebung

- **platform**: Windows-10-10.0.26200-SP0
- **python**: 3.10.20
- **executable**: C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe
- **torch**: 1.12.1+cu113
- **torch.cuda**: 11.3
- **cuda_available**: True
- **device_name**: NVIDIA GeForce GTX 1060
- **device_capability**: (6, 1)
- **total_vram_mb**: 6143.9
- **transformers**: 4.38.2

## Test-Ergebnisse

| Test | Status | Anmerkung |
|---|---|---|
| `baseline` | **ok** |  |
| `clap` | **ok** |  |
| `siglip2` | **ok** |  |
| `coexistence` | **ok** | True |

### `baseline` — ok

- Start: 2026-05-03T11:59:27.518259
- Ende:  2026-05-03T11:59:30.199080
- Snapshots:
  - **baseline_before_torch_init** — allocated=0.0 MB, reserved=0.0 MB, free=5217.0 MB
  - **baseline_after_cuda_init** — allocated=0.0 MB, reserved=2.0 MB, free=4907.0 MB (1-tensor allocated)
  - **baseline_after_empty_cache** — allocated=0.0 MB, reserved=0.0 MB, free=4909.0 MB

### `clap` — ok

- Start: 2026-05-03T11:59:30.201657
- Ende:  2026-05-03T11:59:34.957316
- Metadata:
    - model: `laion/larger_clap_music`
    - skip_inference: `False`
    - feature_shape: `[1, 512]`
    - feature_dim: `512`
- Snapshots:
  - **clap_before_load** — allocated=0.0 MB, reserved=0.0 MB, free=4909.0 MB
  - **clap_after_load** — allocated=742.0 MB, reserved=776.0 MB, free=4133.0 MB
  - **clap_after_processor** — allocated=742.3 MB, reserved=778.0 MB, free=4131.0 MB
  - **clap_after_inference** — allocated=742.3 MB, reserved=808.0 MB, free=3865.0 MB
  - **clap_after_unload_and_empty_cache** — allocated=0.0 MB, reserved=0.0 MB, free=4673.0 MB

### `siglip2` — ok

- Start: 2026-05-03T11:59:34.961336
- Ende:  2026-05-03T12:00:11.619316
- Metadata:
    - model: `google/siglip2-base-patch16-384`
    - batch_sizes_tried: `[1, 2, 4, 8]`
    - batch_results: `{'1': {'status': 'ok', 'vram_allocated_mb': 359.8, 'vram_reserved_mb': 434.0, 'feature_shape': [1, 768]}, '2': {'status': 'ok', 'vram_allocated_mb': 363.4, 'vram_reserved_mb': 506.0, 'feature_shape': [2, 768]}, '4': {'status': 'ok', 'vram_allocated_mb': 369.3, 'vram_reserved_mb': 606.0, 'feature_shape': [4, 768]}, '8': {'status': 'ok', 'vram_allocated_mb': 383.8, 'vram_reserved_mb': 758.0, 'feature_shape': [8, 768]}}`
    - img_size_used: `384`
- Snapshots:
  - **siglip2_before_load** — allocated=0.0 MB, reserved=0.0 MB, free=4673.0 MB
  - **siglip2_after_load** — allocated=355.8 MB, reserved=402.0 MB, free=4271.0 MB
  - **siglip2_batch_1_after_inference** — allocated=359.8 MB, reserved=434.0 MB, free=4239.0 MB (bs=1)
  - **siglip2_batch_2_after_inference** — allocated=363.4 MB, reserved=506.0 MB, free=4167.0 MB (bs=2)
  - **siglip2_batch_4_after_inference** — allocated=369.3 MB, reserved=606.0 MB, free=4067.0 MB (bs=4)
  - **siglip2_batch_8_after_inference** — allocated=383.8 MB, reserved=758.0 MB, free=3915.0 MB (bs=8)
  - **siglip2_after_unload** — allocated=0.0 MB, reserved=0.0 MB, free=4673.0 MB

### `coexistence` — ok

- Start: 2026-05-03T12:00:11.621539
- Ende:  2026-05-03T12:00:15.455344
- Metadata:
    - clap: `laion/larger_clap_music`
    - siglip2: `google/siglip2-base-patch16-384`
    - siglip2_load: `ok`
    - coexistence_possible: `True`
- Snapshots:
  - **coex_before_anything** — allocated=0.0 MB, reserved=0.0 MB, free=4673.0 MB
  - **coex_after_clap_loaded** — allocated=742.0 MB, reserved=776.0 MB, free=3897.0 MB
  - **coex_after_siglip2_loaded** — allocated=1097.5 MB, reserved=1178.0 MB, free=3495.0 MB
  - **coex_after_cleanup** — allocated=0.0 MB, reserved=0.0 MB, free=4673.0 MB

## Synthese (automatisch generiert, Hypothese)

- CLAP + SigLIP-2 **passen gleichzeitig** in den VRAM. Plan-Doc-02-#21 (sequenzieller Lifecycle) bleibt empfohlen fuer Reserve, ist aber nicht zwingend. Dennoch: Demucs + RAFT + NVENC gleichzeitig nicht getestet.

- SigLIP-2 Batch-Stufen:
    - batch=1: ok (VRAM allocated: 359.8 MB)
    - batch=2: ok (VRAM allocated: 363.4 MB)
    - batch=4: ok (VRAM allocated: 369.3 MB)
    - batch=8: ok (VRAM allocated: 383.8 MB)
- **Empfehlung Default-Batch SigLIP-2:** `batch=8` (groesste OK-Stufe), Auto-Tuning bei OOM-Risiko zu kleineren Stufen.

## Vault-Pflege (CLAUDE.md-Pflicht)

Diesen Report kopieren nach:
```
C:\Brain-Bug\projects\pb-studio\wiki\synthesis\
    gpu-coexistence-spike-2026-05-03.md
```

Plus Eintrag in `log.md` mit Verweis auf diesen Spike + Konsequenz fuer Phase-2-DoD (Default-Batch + Coexistenz-Verbot/-Erlaubnis).