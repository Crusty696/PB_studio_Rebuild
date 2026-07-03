# OTK-021 Step 3 Cross-Project Reuse Import Notify - 2026-07-03

Status: product-path live pass, manual GUI click pending

## Scope

Verified OTK-021 step 3 at service + UI-controller product path:

- real ProjectManager project A
- real ProjectManager project B
- same audio file imported into both projects through `ingest_audio`
- project A analysis represented in global by_sha manifest + real stem artifacts
- project B import reused project A analysis immediately
- local `AnalysisStatus(stem_separation)` became `done`
- reused stem paths were attached and exist on disk
- `ImportMediaController._notify_cross_project_reuse()` emitted reuse message
- non-modal reuse notice was created with `Nicht mehr fragen`

This is not a manual GUI click test.

## Evidence

Command:

```powershell
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe scripts\diag\verify_otk021_cross_project_reuse_import_notify.py
```

Result file:

```text
tests/qa_artifacts/otk021_cross_project_reuse_import_notify_result.json
```

Key result:

```json
{
  "status": "pass",
  "checks": {
    "project_a_imported": true,
    "project_b_imported": true,
    "status_done": true,
    "reuse_source_project": "OTK021 Reuse Projekt A",
    "stem_paths_exist": true,
    "toast_message": "Datei wurde bereits in Projekt OTK021 Reuse Projekt A analysiert. Ergebnisse werden mitverwendet.",
    "notice_created": true,
    "notice_non_modal": true,
    "notice_checkbox": "Nicht mehr fragen",
    "mute_value_after_restore": true
  }
}
```

Focused regression:

```powershell
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe -m pytest tests\test_services\test_cross_project_reuse.py tests\ui\test_cross_project_reuse.py -q --basetemp tests\qa_artifacts\pytest-otk021-cross-reuse
```

Result:

```text
17 passed in 9.24s
```

Manifest robustness regression:

```powershell
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe -m pytest tests\test_services\test_manifest_robustness.py -q --basetemp tests\qa_artifacts\pytest-otk021-manifest
```

Result:

```text
8 passed in 2.64s
```

Syntax check:

```powershell
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe -m py_compile services\storage_provenance\source_manifest.py scripts\diag\verify_otk021_cross_project_reuse_import_notify.py
```

Result: Exit 0.

## Code Change

- `scripts/diag/verify_otk021_cross_project_reuse_import_notify.py`
  - New Step-3 verifier.
- `services/storage_provenance/source_manifest.py`
  - Manifest read/write/replace and lock I/O now use Windows long-path-safe filesystem paths.
  - Root cause: focused tests and verifier hit `FileNotFoundError` when `provenance_manifest.json.tmp.<pid>` exceeded Windows MAX_PATH under deep pytest workdirs.

## Honest Limit

This proves real project DBs, real import service path, real by_sha manifest reuse, local green analysis status, and real UI-controller notification creation. It does not prove a human manually clicked through the GUI import dialog.

OTK-021 overall remains open because Steps 1 and 2 still need current product-live evidence, and final `fixed` requires all seven steps plus acceptance criteria.
