# OTK-021 Project Bundle Roundtrip — 2026-06-30

Status: **LOCAL REAL ROUNDTRIP PASS, other-VM import still open**

Scope: OTK-021 90 Live-Verify / Project-Export + Import step 6 partial evidence.

## Command

```powershell
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe scripts\diag\verify_otk021_project_bundle_roundtrip.py
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe -m pytest tests\test_services\test_project_export.py -q
git diff --check
```

## Result

- Project bundle verifier: Exit `0`.
- Project bundle regression tests: `3 passed in 1.36s`.
- `git diff --check`: Exit `0`.

## Evidence

The verifier used the real `ProjectBundleService` with separate file-backed
SQLite databases and separate storage roots:

- export DB: real SQLite file
- import DB: separate real SQLite file
- source storage: real `storage/by_sha`
- target storage: separate real `storage/by_sha`
- bundle: real `.pbbundle` ZIP

Seeded export project:

- project name: `OTK021 Bundle Source Project`
- project resolution/fps: `3840x2160` / `50.0`
- 2 `ProjectSource` rows
- 2 `AnalysisJob` rows:
  - `audio.v2.stems`
  - `video.plan_a.outputs`
- 2 `AnalysisArtifact` rows:
  - `vocals_stem`
  - `edit_proxy`
- 2 real storage files under `storage/by_sha`

Verified after import:

- export result: `source_count=2`, `job_count=2`, `artifact_count=2`, `file_count=2`
- import result: `source_count=2`, `job_count=2`, `artifact_count=2`, `file_count=2`
- imported project count: `1`
- imported project name preserved
- imported project path overridden to the target import path
- imported job steps preserved
- imported artifact roles preserved
- restored file SHA256 values exactly matched source files
- manifest contains project metadata, two sources, two jobs, two artifacts,
  and two storage file entries
- ZIP contains `manifest.json` and both storage files

Artifact:

- `tests/qa_artifacts/otk021_project_bundle_roundtrip_result.json`

## Honest Limit

This proves a local real `.pbbundle` export/import roundtrip using the service,
real SQLite files, and real storage files. It does **not** prove import on a
different VM, installer-installed app behavior, or production rollout readiness.
OTK-021 step 6 remains incomplete until other-VM import is actually run or
explicitly re-decided by the user.
