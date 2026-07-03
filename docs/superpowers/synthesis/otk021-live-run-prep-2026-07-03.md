---
status: prep-pass
task: OTK-021 live-run-prep
date: 2026-07-03
---

# OTK-021 Live Run Prep - 2026-07-03

No long run started.

## Matrix

| Step | Area | Prep evidence | Long-run proof target |
|---|---|---|---|
| 1 | Migration | mini service prep run | migration.audio_tracks == 1; by_sha stem link exists |
| 2 | SCHNITT audio adapter | mini service prep run | adapter links stems; manifest fallback separately checks non-wav stem paths |
| 3 | Cross-Project-Reuse | DB + manifest prep runs | DB reuse toast/status plus separate manifest fallback with flac paths |
| 4 | File-Tracking | mini service run | moved file repaired by SHA |
| 5 | Storage-Browser | visible verifier rerun | row 1 -> 0; source root true -> false |
| 6 | Project-Bundle VM | existing VM proof checked | otk021_vm_portability_probe.json project_bundle_ok true |
| 7 | Backup/Restore VM | existing VM proof checked | otk021_vm_portability_probe.json backup_restore_ok true |

## Results

- Dry-run imports: `True`.
- Data preflight: `True`.
- FFmpeg GPU command: `-hwaccel cuda`, `h264_nvenc`, `128x128`.
- Disk free bytes: `27812114432`.
- Disk warning: `None`.
- Mini service prep run: `True`.
- Manifest fallback reuse prep: `True`.
- Storage-Browser visible verifier: `True`.
- VM proof check: `True`.
- Stale prep artifacts removed: `4`.
- Heartbeat: `C:\Users\David_Lochmann\Documents\PB_studio_Rebuild\PB_studio_Rebuild\tests\qa_artifacts\otk021_live_prep_heartbeat.json`.
- Watch config: `C:\Users\David_Lochmann\Documents\PB_studio_Rebuild\PB_studio_Rebuild\tests\qa_artifacts\otk021_live_log_watch_config.json`.
- Watch patterns: `['Traceback', 'ERROR', 'CRITICAL', 'CUDA out of memory', 'out of memory', 'OOM', 'sqlite3.OperationalError', 'Conversion failed', 'Error while opening encoder', 'InitializeEncoder failed']`.

## Honest Limit

Prep proves wiring and prerequisites for a long live run. It does not replace the long product-live verification and does not allow `fixed`.

## Open / Not Verified

- No long product-live verification started in this prep step.
- Steps 1-4 still need long product-live proof with real migrated project data.
- This document is `prep-pass`, not `fixed`.
