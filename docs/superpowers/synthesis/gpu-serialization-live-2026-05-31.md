---
type: synthesis
title: GPU Serialization Live Gate - 2026-05-31
status: code-fix-pending-live-verification
plan_id: PB-STUDIO-FULL-AUDIT-FIXPLAN-2026-05-31
task: Task 8 - GPU Serialization Verification Gate
date: 2026-06-01
---

# GPU Serialization Live Gate - 2026-05-31

## Task Quote

`Task 8 - GPU Serialization Verification Gate`

## Summary

Task 8 added `tests/test_services/test_gpu_lock_contract.py`.

The contract test verifies:

- `ModelManager.ensure_loaded()` uses `gpu_resource_lease`.
- Brain V3 `GpuSerializer` bridges to `services.model_manager.GPU_EXECUTION_LOCK`.
- `SigLipEmbedStage.run()` uses the default GPU serializer around embedding work.
- `RaftMotionStage.run()` uses the default GPU serializer around RAFT flow work.

No app-code change was required by this gate.

## Commands Run

```powershell
& "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/test_services/test_gpu_lock_contract.py tests/test_services/test_video_model_services.py -v
& "C:\Users\David Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests/test_services/test_video_pipeline_e2e_live.py -m live_gpu -v
```

## Results

| Gate | Result | Notes |
|---|---:|---|
| GPU lock contract + video model services | 14 passed, 3 warnings in 35.83s | Includes SigLIP and RAFT service live_gpu tests because they are in the target file. |
| Video pipeline live_gpu E2E | 3 passed, 4 warnings in 38.53s | CUDA path available on active PB Studio env. |

## Warnings Observed

- `huggingface_hub.file_download`: `resume_download` future deprecation.
- PyTorch warning in `raft_motion_service.py`: NumPy array is not writable before `torch.from_numpy`.
- SWIG deprecation warnings from imported native modules.

These warnings did not fail the gate.

## Verification Status

- Unit lock contract: passed.
- GPU service live tests: passed.
- GPU pipeline live test: passed.
- Manual app/UI workflow: not run.
- `fixed` status: not written.

Status remains `code-fix-pending-live-verification` because no manual app workflow was executed.
