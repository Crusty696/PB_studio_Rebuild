# Brain V3 — Phase-0-Spike: GPU-Coexistenz

**Generiert:** 2026-05-03T11:56:32.244213  
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
| `siglip2` | **error** | TypeError: expected str, bytes or os.PathLike object, not NoneType |
| `coexistence` | **error** | Coexistenz-Test fehlgeschlagen, kein OOM |

### `baseline` — ok

- Start: 2026-05-03T11:55:51.135523
- Ende:  2026-05-03T11:55:57.549302
- Snapshots:
  - **baseline_before_torch_init** — allocated=0.0 MB, reserved=0.0 MB, free=5217.0 MB
  - **baseline_after_cuda_init** — allocated=0.0 MB, reserved=2.0 MB, free=4907.0 MB (1-tensor allocated)
  - **baseline_after_empty_cache** — allocated=0.0 MB, reserved=0.0 MB, free=4909.0 MB

### `clap` — ok

- Start: 2026-05-03T11:55:57.552973
- Ende:  2026-05-03T11:56:25.674756
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

### `siglip2` — error

- Start: 2026-05-03T11:56:25.674756
- Ende:  2026-05-03T11:56:28.155394
- Fehler: `TypeError: expected str, bytes or os.PathLike object, not NoneType`
- Metadata:
    - model: `google/siglip2-base-patch16-384`
    - batch_sizes_tried: `[1, 2, 4, 8]`
    - batch_results: `{}`
- Snapshots:
  - **siglip2_before_load** — allocated=0.0 MB, reserved=0.0 MB, free=4673.0 MB

### `coexistence` — error

- Start: 2026-05-03T11:56:28.162645
- Ende:  2026-05-03T11:56:32.244213
- Fehler: `Coexistenz-Test fehlgeschlagen, kein OOM`
- Metadata:
    - clap: `laion/larger_clap_music`
    - siglip2: `google/siglip2-base-patch16-384`
    - siglip2_load: `TypeError: expected str, bytes or os.PathLike object, not NoneType`
    - coexistence_possible: `False`
    - siglip2_oom: `False`
- Snapshots:
  - **coex_before_anything** — allocated=0.0 MB, reserved=0.0 MB, free=4673.0 MB
  - **coex_after_clap_loaded** — allocated=742.0 MB, reserved=776.0 MB, free=3897.0 MB
  - **coex_siglip2_load_failed** — allocated=742.0 MB, reserved=776.0 MB, free=3897.0 MB
  - **coex_after_cleanup** — allocated=0.0 MB, reserved=0.0 MB, free=4673.0 MB

## Synthese (automatisch generiert, Hypothese)

- Coexistenz-Test inkonklusiv (nicht-OOM-Fehler). Manuelle Pruefung des Logs noetig.

## Vault-Pflege (CLAUDE.md-Pflicht)

Diesen Report kopieren nach:
```
C:\Brain-Bug\projects\pb-studio\wiki\synthesis\
    gpu-coexistence-spike-2026-05-03.md
```

Plus Eintrag in `log.md` mit Verweis auf diesen Spike + Konsequenz fuer Phase-2-DoD (Default-Batch + Coexistenz-Verbot/-Erlaubnis).