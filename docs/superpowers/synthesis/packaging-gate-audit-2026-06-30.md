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
  - vor Prune: 14,802 Dateien, 8.83 GB
  - nach Prune: 14,758 Dateien, 5.52 GB
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
  - Belegt nach Prune: dist, exe, Qt DLLs, CUDA/Torch DLL patterns, assets, runtime dirs, FFmpeg/ffprobe, total size.
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
- NSIS / NSISBI:
  - Standard NSIS `makensis` was installed via winget (`NSIS.NSIS` 3.12), but it failed for this large payload:
    - before Prune: `Internal compiler error #12345: error mmapping datablock to 2453204`
    - after Prune: `Internal compiler error #12345: error mmapping datablock to 33588998`
  - NSISBI 7069-1 was downloaded from
    `downloads.sourceforge.net/project/nsisbi/nsisbi3.04.1/nsis-binary-7069-1.zip`
    and copied to `%LOCALAPPDATA%\PBStudioTools\nsisbi-7069-1`.
  - NSISBI ZIP SHA256:
    `21823151EF3EB5BB2745C12ED0655D83E84EE1404AEDCA31368229DFDFD824AB`
  - NSISBI `/HDRINFO` confirmed `NSIS_CONFIG_EXTERNAL_FILE_SUPPORT`.
  - Command: `NSISBI makensis /V2 /DUSE_NSISBI installer/pb_studio.nsi`
  - Result: Exit `0`
  - Artifacts:
    - `dist/pb_studio_setup_v0.5.0.exe` = 422,872 bytes
    - `dist/pb_studio_setup_v0.5.0.nsisbin` = 2,816,861,307 bytes
  - Signature check: `Get-AuthenticodeSignature` = `NotSigned`
  - Build script proof:
    - Command: `PB_SKIP_PYINSTALLER=1 cmd /c installer\build_installer.bat`
    - Result: Exit `0`, target runtime check green, prune green, smoke green, local NSISBI used, installer created.

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
- `installer/hooks/runtime_hook_torch.py`:
  - adds package-local DLL directories (`torch/lib`, `torch/bin`, `torchvision`, `PySide6`) to `PATH`
- `installer/prune_pyinstaller_dist.py`:
  - removes duplicated top-level DLL/PYD files only when a package-local copy remains
- `installer/build_installer.bat`:
  - target Python 3.10/cu113 runtime is enforced
  - PyInstaller must be pinned at `6.20.0`; no unpinned auto-install
  - prune script runs before smoke
  - NSISBI is used automatically from `%LOCALAPPDATA%\PBStudioTools\nsisbi-7069-1\Bin\makensis.exe`
  - `PB_SKIP_PYINSTALLER=1` can package an existing `dist/pb_studio`
- `installer/pb_studio.nsi`:
  - optional `/DUSE_NSISBI` mode uses external-payload output
  - `StrContains` macro order/call fixed
- `docs/DEPLOYMENT.md` and `installer/DEPLOYMENT_CHECKLIST.md`:
  - document the NSISBI two-file installer (`.exe` + `.nsisbin`) and current pruned size

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
- Standard NSIS cannot package the current payload; release build uses NSISBI two-file output.
- NSISBI binary is installed locally on this build machine, not vendored in the repo.

## Blocker

- No clean Windows VM install test exists.
- No signed installer exists.
- Frozen build has only launch smoke, not full user workflow smoke.
- Installer exists but has not been installed or launched from a clean machine.
- Installer output is a two-file package; release packaging must ship `.exe` and `.nsisbin` together.
- PyInstaller warning set still needs triage before release claim.
- DG-001 still blocks release status pending user decision on H1 replacement medium.

## Warntriage Update — 2026-06-30

Command:

```powershell
cmd /c installer\build_installer.bat 2>&1 | Tee-Object -FilePath test-report\packaging-build-warntriage-filtered-20260630.log
```

Result: Exit `0`; PyInstaller build, duplicate-DLL prune, smoke test, and
NSISBI installer creation completed.

Changed:

- `pb_studio.spec` removes stale explicit hidden import `workers.debug`.
- `pb_studio.spec` filters known unused hidden imports after collection and
  excludes `torch.distributed`, `torch.utils.tensorboard`,
  `pyqtgraph.opengl`, and `PySide6.scripts.deploy_lib`.

Verified:

- New build log does not contain the stale `workers.debug` warning.
- `dist/pb_studio_setup_v0.5.0.exe` and
  `dist/pb_studio_setup_v0.5.0.nsisbin` were regenerated.
- Smoke test passed after prune with dist size `5.52 GB`.

Still open:

- `torch.distributed.*` hidden-import warnings remain. Evidence in
  `build/pb_studio/warn-pb_studio.txt` shows imports from torch internal test
  and optional distributed integration paths.
- `torch.utils.tensorboard`, `torch.utils.benchmark`, and
  `pyqtgraph.opengl` collection warnings remain from PyInstaller/contrib hook
  collection, not from direct PB Studio source imports.
- Missing optional DLL warnings remain for Qt SQL drivers, Qt WebView QML,
  ONNX Runtime TensorRT provider, Numba TBB pool, and torchaudio FFmpeg
  extension DLLs.

Honest status: warning triage is **partial**. One stale app hidden import was
removed and the build still passes, but the PyInstaller warning output is not
release-clean and must not be called resolved.

## Hook-Filtered Warntriage Update — 2026-06-30

Command:

```powershell
cmd /c installer\build_installer.bat 2>&1 | Tee-Object -FilePath test-report\packaging-build-hookfiltered3-20260630.log
```

Result: Exit `0`; PyInstaller build, duplicate-DLL prune, smoke test, and
NSISBI installer creation completed.

Changed:

- `installer/hooks/hook-torch.py` now filters non-runtime torch submodule
  collection for `torch.distributed`, `torch.testing`,
  `torch.utils.benchmark`, and `torch.utils.tensorboard`.
- `installer/hooks/hook-pyqtgraph.py` was added to collect pyqtgraph runtime
  templates/bootstrap while excluding `pyqtgraph.examples`,
  `pyqtgraph.jupyter`, and `pyqtgraph.opengl`.
- `pb_studio.spec` applies the same non-runtime torch filters and excludes.

Verified:

- `test-report/packaging-build-hookfiltered3-20260630.log` no longer contains
  failed-collection warnings for `torch.utils.tensorboard`,
  `torch.utils.benchmark`, `pyqtgraph.opengl`, or `pyqtgraph.jupyter`.
- It no longer contains the previous `torch.distributed.*` hidden-import flood.
- `SMOKE_TEST_LAUNCH=1 installer/smoke_test.py` exited `0`; the frozen EXE
  launched and was terminated after the 5s smoke timeout.
- Regenerated artifacts:
  - `dist/pb_studio_setup_v0.5.0.exe` = `423,231` bytes
  - `dist/pb_studio_setup_v0.5.0.nsisbin` = `2,816,073,535` bytes
  - EXE SHA256:
    `560B1321158AD524A4BEEE3D43973BE9C1B6B1BE9B316CA62E2D73C589A2A3DA`
  - NSISBIN SHA256:
    `3BB9E7C2423EF0A11CAC02D1A9E18CFC7E14DA0F452BFAFCE7C8462AE2EF2123`
  - Authenticode: `NotSigned`

Still open:

- Hidden import warnings remain for `pycparser.lextab`, `pycparser.yacctab`,
  `tzdata`, `scipy.special._cdflib`, `pysqlite2`, and `MySQLdb`.
- Missing optional DLL warnings remain for Qt SQL drivers, Qt WebView QML,
  ONNX Runtime TensorRT provider, Numba TBB pool, and torchaudio FFmpeg
  extension DLLs.
- `build/pb_studio/warn-pb_studio.txt` still lists indirect missing
  `torch.distributed.*` modules from conditional/optional paths, even though
  the build log no longer shows the previous explicit hidden-import flood.

Honest status: warning triage is **improved but still partial**. The noisy
torch/pyqtgraph collection warnings were removed and the build still passes,
but the warning set is not clean enough for a release-ready claim.

## Optional Artifact Warntriage Update — 2026-06-30

Commands:

```powershell
cmd /c installer\build_installer.bat 2>&1 | Tee-Object -FilePath test-report\packaging-build-onnxfiltered-20260630.log
SMOKE_TEST_LAUNCH=1 python installer\smoke_test.py
python -m pytest tests\test_services\test_bundle_hooks.py tests\test_b427_ffmpeg_check.py tests\test_services\test_b563_startup_nvenc_gate.py tests\test_services\test_ai_audio_service.py tests\test_services\test_stem_separator_audio_decode.py tests\test_services\test_brain_v3_onnx_eval.py -q
python tools\release_gate.py
```

Result:

- Full build: Exit `0`; PyInstaller build, prune, smoke, and NSISBI installer
  creation completed.
- Launch smoke: Exit `0`; frozen EXE launched and was terminated after 5s.
- Focus regression: `38 passed in 66.39s`.
- Release gate: Exit `1`, still blocked by DG-001 H1 replacement-medium user
  decision.

Changed:

- `pb_studio.spec` filters optional PySide6 QtSql Mimer/Postgres plugin
  binaries, QtWebView QML payload, Numba TBB pool extension, and optional
  hidden imports for pycparser tables, tzdata, scipy cdflib, pysqlite2, and
  MySQLdb.
- `installer/hooks/hook-onnxruntime.py` was added to collect ONNX Runtime
  dynamic libraries while excluding `onnxruntime_providers_tensorrt.dll`.
  PB Studio's active ONNX path requires `CUDAExecutionProvider` and
  `CPUExecutionProvider`, not TensorRT.

Verified:

- `test-report/packaging-build-onnxfiltered-20260630.log` no longer contains
  QtSql Mimer/Postgres, QtWebView QML, TensorRT, TBB, pycparser, tzdata,
  scipy cdflib, pysqlite2, or MySQLdb build-log warnings.
- Remaining build-log warnings are torchaudio FFmpeg extension DLLs only:
  `avformat-58.dll`, `avutil-56.dll`, `avdevice-58.dll`, `avcodec-58.dll`,
  and `avfilter-7.dll`.
- Regenerated artifacts:
  - `dist/pb_studio_setup_v0.5.0.exe` SHA256:
    `AD3A5182767E3A41C99969D38F1B662D6B7129022B6C2DD0CC5E784362EF33FF`
  - `dist/pb_studio_setup_v0.5.0.nsisbin` SHA256:
    `23DC12FA7B98F053A515B6D0302CD823266D6B7F57C3E0F5EF55F2C0CDBA1FA3`
  - Authenticode remains `NotSigned`.

Honest status: warning triage is still **partial**. The build log is much
cleaner, but torchaudio FFmpeg extension warnings remain. Because PB Studio
uses torchaudio in audio workflows, those binaries were not removed without a
stronger frozen audio workflow proof.

## Honest Release Status

Packaging is **partially verified**, not release-ready. The PyInstaller onedir
build now exists and passes static + launch smoke in the correct Python
3.10/cu113 target runtime after pruning duplicated DLLs. Export/convert paths
pass with a synthetic NVENC fixture. A NSISBI installer stub and external
payload now build successfully, but clean-machine installation, signing,
warning triage, DG-001 user decision, and full frozen GUI workflow remain open.
