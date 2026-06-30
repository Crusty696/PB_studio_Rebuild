# Packaging Gate Audit — 2026-06-30

Status: **PARTIAL, weiter BLOCKED fuer Release**

Scope: OTK-021 90 Live-Verify / Release-Readiness Packaging-Gate.

## Belege

- Zielruntime explizit geprueft:
  - `C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe`
  - Python `3.10.20`
  - torch `1.12.1+cu113`, CUDA `11.3`, CUDA available `True`
  - GPU `NVIDIA GeForce GTX 1060`
  - SQLAlchemy `2.0.51`, PySide6 `6.7.3`
  - PyInstaller `6.20.0`
- Falscher Zwischenstand wurde erkannt und verworfen:
  - Bare `python` zeigte auf Conda base Python `3.13.13`.
  - Der erste `dist/`-Build war deshalb nicht release-gueltig.
  - `build/` und `dist/` wurden geloescht und mit Zielruntime neu gebaut.
- Zielruntime-Build:
  - Command: `C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe -m PyInstaller pb_studio.spec --noconfirm --log-level WARN`
  - Result: Exit `0`
  - PyInstaller output bestaetigte Python `3.10.20 (conda)` und env `pb-studio`.
- Zielbuild-Artefakte:
  - `dist/pb_studio/pb_studio.exe`
  - `dist/pb_studio/_internal`
  - `dist/pb_studio/_internal/bin/ffmpeg.exe`
  - `dist/pb_studio/_internal/bin/ffprobe.exe`
  - `resources`, `knowledge`, `config`, `translations`
  - `database/alembic`
  - `services/brain/storage/sql_migrations`
  - 14,802 Dateien, 8.83 GB
- CUDA/Torch DLLs im Bundle gefunden:
  - `c10_cuda.dll`
  - `cublas64_11.dll`
  - `cublasLt64_11.dll`
  - `cudart64_110.dll`
  - `cudnn64_8.dll`
  - `torch_cuda_cpp.dll`
  - `torch_cuda_cu.dll`
- Frozen smoke:
  - Command: `pb-studio python installer/smoke_test.py`
  - Result: Exit `0`, `Smoke test passed.`
  - Belegt: dist, exe, Qt DLLs, CUDA/Torch DLL patterns, assets, runtime dirs, FFmpeg/ffprobe, total size.
- Frozen launch smoke:
  - Command: `SMOKE_TEST_LAUNCH=1 pb-studio python installer/smoke_test.py`
  - Result: Exit `0`, EXE started and was terminated after 5s timeout.
  - Grenze: Start-Smoke, kein Full-GUI-Workflow.
- Export/Convert/NVENC script test:
  - Fixture: `test-report/fixtures/packaging_export_fixture_720p5s.mp4`
  - Fixture command used `bin/ffmpeg.exe` with `h264_nvenc`.
  - Command: `PB_TEST_VIDEO_PATH=<fixture> pb-studio python tests/test_export_convert_real.py`
  - Result: Exit `0`, 21/21 PASS, 0 FAIL, 0 CRASH.
  - Belegt: `detect_nvenc()` h264/hevc/cuda true, convert edit/master/davinci, export timeline, preview export, TimelineService, auto-edit export.
  - Grenze: synthetic fixture, not historical H1/user footage.
- NSIS:
  - `where makensis` result: not found.
  - Installer build remains blocked.

## Changes Made

- `requirements-py310-cu113.txt`: added reproducible build pins:
  - `pyinstaller==6.20.0`
  - `pyinstaller-hooks-contrib==2026.5`
- `pb_studio.spec`: corrected Brain SQL migration data path:
  - from `services/brain_v3/storage/sql_migrations`
  - to `services/brain/storage/sql_migrations`
- `installer/smoke_test.py`:
  - nonfatal `[FAIL]` checks now make final process exit `1`
  - PyInstaller 6 onedir size sanity now checks EXE >=10 MB and full dist >=1 GB
- `tests/test_export_convert_real.py`:
  - `PB_TEST_VIDEO_PATH` can override the stale hard-coded source video
  - any FAIL/CRASH now exits `1`
- `.gitignore`:
  - ignores generated PyInstaller `build/` and `dist/` directories

## Open Warnings

PyInstaller exited `0`, but warning output is not clean. These warnings are not proven harmless:

- many missing `torch.distributed.*` hidden imports
- hidden import `workers.debug` not found
- optional/missing DLLs:
  - `MIMAPI64.dll`
  - `LIBPQ.dll`
  - `Qt6WebViewQuick.dll`
  - TensorRT DLLs: `nvonnxparser_10.dll`, `nvinfer_plugin_10.dll`, `nvinfer_10.dll`
  - `tbb12.dll`
  - torchaudio FFmpeg DLLs: `avformat-58.dll`, `avutil-56.dll`, `avdevice-58.dll`, `avcodec-58.dll`, `avfilter-7.dll`

## Blocker

- No NSIS installer exists; `makensis` is missing.
- No clean Windows VM install test exists.
- No signed installer exists.
- Frozen build has only launch smoke, not full user workflow smoke.
- PyInstaller warning set still needs triage before release claim.
- DG-001 still blocks release status pending user decision on H1 replacement medium.

## Honest Release Status

Packaging is **partially verified**, not release-ready. The PyInstaller onedir
build now exists and passes static + launch smoke in the correct Python
3.10/cu113 target runtime. Export/convert paths pass with a synthetic NVENC
fixture. Installer generation, clean-machine validation, signing, warning
triage, DG-001 user decision, and full frozen GUI workflow remain open.
