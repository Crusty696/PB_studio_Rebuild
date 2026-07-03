# OTK-021 Step 4 File Tracking Open-Project Live Evidence - 2026-07-03

Status: product-path live pass, GUI live pending

## Scope

Verified OTK-021 step 4 at the app service/product path:

- create real project folder
- create real `pb_studio.db`
- insert stale `project_sources.current_source_path`
- place moved source file inside the project folder
- call `ProjectManager.open_project(project_dir)`
- verify `ProjectSource.current_source_path` is repaired by content SHA

This is not a manual GUI click test.

## Evidence

Command:

```powershell
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe scripts\diag\verify_otk021_file_tracking_open_project.py
```

Result file:

```text
tests/qa_artifacts/otk021_file_tracking_open_project_result.json
```

Key result:

```json
{
  "status": "pass",
  "checks": {
    "repaired_path_exists": true,
    "repaired_to_moved_source": true,
    "open_project_returned_name": "OTK021 File Tracking Open"
  }
}
```

Unit tests:

```powershell
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe -m pytest tests\test_services\test_file_tracking.py -q --basetemp tests\qa_artifacts\pytest-otk021-filetracking
```

Result:

```text
3 passed in 1.63s
```

Syntax check:

```powershell
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe -m py_compile services\project_manager.py services\storage_provenance\file_tracking.py tests\test_services\test_file_tracking.py scripts\diag\verify_otk021_file_tracking_open_project.py
```

Result: Exit 0.

## Code Change

- `services/project_manager.py`
  - `open_project()` now calls file-tracking repair after DB switch.
  - Repair searches only inside the opened project folder.
  - Single-project DBs are supported even if the stored `Project.path` is stale after copy/import.
  - Multi-project DBs are scoped to matching project path.
- `services/storage_provenance/file_tracking.py`
  - `repair_missing_sources()` accepts optional `source_ids`.
  - Default behavior is unchanged.
- `tests/test_services/test_file_tracking.py`
  - Added coverage for open-project repair scope.
- `scripts/diag/verify_otk021_file_tracking_open_project.py`
  - Added product-path verifier.

## Honest Limit

This proves the `ProjectManager.open_project()` path. It does not prove the full manual GUI workflow. OTK-021 Step 4 can be counted as product-path live pass, not full GUI verified.

OTK-021 overall remains open because Steps 1-3 still need product-live evidence.
