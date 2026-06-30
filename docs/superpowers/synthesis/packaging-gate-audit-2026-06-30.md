# Packaging Gate Audit — 2026-06-30

Status: **BLOCKED, nicht release-ready**

Scope: OTK-021 90 Live-Verify / Release-Readiness Packaging-Gate.

## Belege

- Packaging files exist:
  - `pb_studio.spec`
  - `installer/build_installer.bat`
  - `installer/smoke_test.py`
  - `installer/pb_studio.nsi`
  - `pb_packaging/bundle_hooks.py`
  - `docs/DEPLOYMENT.md`
- No build artifact exists in repo root:
  - no `dist/pb_studio`
  - no `build/pb_studio`
- `python installer/smoke_test.py` exits `1`:
  - `[FAIL] dist folder exists`
- `python -c "import PyInstaller"` in the active `pb-studio` env exits `1`:
  - `ModuleNotFoundError: No module named 'PyInstaller'`
- Focus tests:
  - `python -m pytest tests/test_services/test_bundle_hooks.py tests/test_b427_ffmpeg_check.py tests/test_services/test_b563_startup_nvenc_gate.py -q`
  - Result: `9 passed in 4.09s`
- Active torch CUDA DLLs under `C:\Users\David_Lochmann\miniconda3\envs\pb-studio\Lib\site-packages\torch\lib`:
  - `cudart64_110.dll`
  - `cublas64_11.dll`
  - `cublasLt64_11.dll`
  - `cudnn64_8.dll`
  - `torch_cuda.dll`
  - `torch_cuda_cu.dll`
  - `torch_cuda_cpp.dll`

## Changes Made

- `pb_studio.spec`: added active cu113/torch CUDA DLL names to `upx_exclude`.
- `docs/DEPLOYMENT.md`: removed stale `styles/` bundle reference and corrected size check to measure the full onedir bundle.
- `installer/DEPLOYMENT_CHECKLIST.md`: aligned checklist with active Python 3.10 / torch cu113 / GTX 1060 release path and removed stale Python 3.11/3.12, CUDA 12.4, and `styles/` requirements.

## Blocker

- No PyInstaller build exists.
- PyInstaller is not installed in the active `pb-studio` env.
- No NSIS installer exists.
- No frozen executable smoke exists.
- No clean Windows VM install test exists.
- No signed installer exists.

## Honest Release Status

Packaging is **not verified** and **not release-ready**. The current work only
aligns Packaging documentation/spec guardrails with the active runtime and
records the missing evidence. A real release still needs a full PyInstaller
build, installer build, smoke test, and clean-machine launch/workflow test.

