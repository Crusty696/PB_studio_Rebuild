# OTK-021 Backup/Restore Portable Verify — 2026-06-30

Status: **LOCAL REAL ROUNDTRIP PASS, VM restore still open**

Scope: OTK-021 90 Live-Verify / Backup-Portability step 7 partial evidence.

## Command

```powershell
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe scripts\diag\verify_otk021_backup_restore_portable.py
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe -m pytest tests\test_services\test_backup.py -q
git diff --check
```

## Result

- Portable backup/restore verifier: Exit `0`.
- Backup regression tests: `2 passed in 1.09s`.
- `git diff --check`: Exit `0`.

## Evidence

The verifier used the real `StoragePortabilityBackupService` with:

- temporary real SQLite DB in WAL mode
- `PRAGMA user_version=21`
- table row `sample.value = 'wal-visible'`
- temporary real `storage/by_sha` root
- two real storage files:
  - `storage/by_sha/aa/<sha>/audio/stem.wav`
  - `storage/by_sha/bb/<sha>/video/proxy.mp4`

Verified after restore:

- backup storage file count: `2`
- restore storage file count: `2`
- restored DB `user_version`: `21`
- restored DB value: `wal-visible`
- restored file SHA256 values exactly matched source files
- manifest `db_schema_version`: `otk021-live`
- manifest `storage_layout_version`: `1`
- manifest `model_versions`: `{"demucs": "4.0.1", "siglip": "so400m"}`
- zip contained `manifest.json`, `database/pb_studio.db`, and both storage files.

Artifact:

- `tests/qa_artifacts/otk021_backup_restore_portable_result.json`

## Honest Limit

This proves a local real portable backup/restore roundtrip using the service
and real files. It does **not** prove restore on another VM, installer-installed
app behavior, or production rollout readiness. OTK-021 step 7 remains
incomplete until VM restore is actually run or explicitly re-decided by the
user.
