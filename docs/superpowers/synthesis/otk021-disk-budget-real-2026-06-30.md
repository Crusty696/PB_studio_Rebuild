# OTK-021 Disk-Budget-71 Local Real Service Verification 2026-06-30

Status: `local-real-service-pass-vm-app-live-open`

## Scope

OTK-021 / 71 Disk-Budget Global wurde lokal ueber den echten
`DiskBudgetService` gegen eine echte SQLite-Datei und echte
`storage/by_sha`-Dateien geprueft.

Das ist kein Clean-VM-Test, kein installierter-App-Test und kein vollstaendiger
Storage-Browser-Produktworkflow.

## Commands

```powershell
& "C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe" -m py_compile scripts\diag\verify_otk021_disk_budget_real.py
& "C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe" scripts\diag\verify_otk021_disk_budget_real.py
& "C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe" -m pytest tests\test_services\test_disk_budget_global.py -q
git diff --check
& "C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe" tools\release_gate.py
```

## Results

- `py_compile`: Exit 0.
- `scripts/diag/verify_otk021_disk_budget_real.py`: Exit 0.
- Result artifact: `tests/qa_artifacts/otk021_disk_budget_real_result.json`.
- `tests/test_services/test_disk_budget_global.py -q`: `3 passed in 1.17s`.
- `git diff --check`: Exit 0.
- `tools/release_gate.py`: Exit 1, expected current block on DG-001 H1 replacement-medium user decision.

## Evidence

Verifier created:

- file-backed SQLite DB:
  `tests/qa_artifacts/otk021_disk_budget_real/disk_budget.sqlite`
- real storage root:
  `tests/qa_artifacts/otk021_disk_budget_real/storage`
- four real `storage/by_sha` source roots with artifact files
- two real projects
- two used sources
- one old unused source
- one recent unused source

Service output:

- `summary.total_bytes = 10000`
- `summary.source_count = 4`
- `project_usage["Disk Budget A"] = 4000`
- `project_usage["Disk Budget B"] = 2000`
- cleanup estimate returned only old unused source
- `cleanup_estimate.reclaimable_bytes = 3000`
- real free-space probe passed with `required_bytes = 1`
- low-space guard raised:
  `Not enough free disk space for migration: required=11, free=10`

## Honest Limits

- DiskBudgetService sums DB `AnalysisArtifact.bytes`, not filesystem byte
  sizes. The verifier records both DB bytes and actual file sizes to avoid
  pretending these are identical.
- Low-space failure branch is tested by patched `disk_usage(free=10)`.
  Filling the disk was intentionally not done.
- No Clean-VM run.
- No installed-app run.
- No user `fixed` marker.
- Release remains blocked by DG-001.
