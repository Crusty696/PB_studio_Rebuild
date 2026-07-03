---
status: cleanup-partial-pass
task: cleanup-old-runs-models
date: 2026-07-03
---

# Cleanup Old Runs / Models - 2026-07-03

## Deleted

| Path | Reason | Freed |
|---|---|---|
| `outputs/test66666` | Old generated PB Studio test project/run; `outputs/` is git-ignored. | `12.879 GB` |
| `build/pb_studio` | Generated PyInstaller build cache; `build/` is git-ignored and rebuildable. | part of `0.143 GB` |
| `outputs/test555` | Old tiny generated test project; `outputs/` is git-ignored. | part of `0.143 GB` |
| `outputs/test_imported` | Old tiny generated test project; `outputs/` is git-ignored. | part of `0.143 GB` |

Total measured cleanup gain: `13.022 GB`.

Disk after cleanup: `25.90 GB` free by `Get-PSDrive C`.

## Reverified After Cleanup

`scripts/diag/prepare_otk021_live_run.py` passed after cleanup.

- `data_preflight.disk.free_bytes`: `27812114432`
- `data_preflight.disk.warning`: `null`
- NVENC/CUDA mini video: `-hwaccel cuda`, `h264_nvenc`, `128x128`
- Mini service prep: `ok=true`
- Manifest fallback reuse with `.flac` stems: `ok=true`
- Storage-Browser visible verifier: `ok=true`
- VM proof check: `ok=true`

## Not Deleted

| Path | Size | Reason |
|---|---:|---|
| `dist/` | `10.764 GB` | Current release/distribution artifacts; needed for rollout evidence. |
| `%LOCALAPPDATA%/PB Studio` | `5.516 GB` | Installed app/runtime proof target; deleting would break installed-app verification. |
| `%USERPROFILE%/.ollama` | `11.113 GB` | App has Ollama integration; not proven unused. |
| `%USERPROFILE%/.cache/huggingface` | `8.996 GB` | Contains SigLIP/moondream/CLAP model caches; not proven unused. |
| `%USERPROFILE%/.cache/torch` | `0.471 GB` | PyTorch cache; not proven unused. |
| `PB_studio_Rebuild_github_compare_DEPRECATED_DO_NOT_USE` | `7.664 GB` | Deprecated duplicate, but dirty: modified and untracked files exist. Not deleted to avoid losing unknown work. |

## Honest Limit

Cleanup removed old generated run data and build cache. It did not remove model
caches because their non-use was not proven. It did not delete the deprecated
duplicate checkout because its dirty state could contain uncommitted work.
