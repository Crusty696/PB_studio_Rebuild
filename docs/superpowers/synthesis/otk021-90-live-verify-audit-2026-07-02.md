---
status: partial-pass-open
task: OTK-021 90 Live-Verify
date: 2026-07-02
fixed_marker_allowed: false
---

# OTK-021 90 Live-Verify Audit - 2026-07-02

## Task Quote

Source: `docs/superpowers/archive/2026-05-19-global-storage-provenance/90_LIVE_VERIFY.md`

1. Migration: existing V2 + Plan-A data registered into `by_sha/` via junctions.
2. SCHNITT audio subtab still works without code touch.
3. Cross-Project-Reuse: same file in two projects -> notify toast, analyses immediately green.
4. File-Tracking: moved file -> app finds it again via SHA.
5. Storage-Browser: all files visible, bulk delete works.
6. Project-Export + Import on another VM.
7. Backup + Restore on VM.

Acceptance: all seven steps without stacktrace, SCHNITT functional, V2 pipeline still writes provenance. Only then `fixed`.

## Current Evidence

| Step | Current status | Evidence | Honest limit |
|---|---|---|---|
| 1 Migration | partial | 2026-06-18 audit says migration/caller path was rechecked via `open_project` / `record_done`; current focused regression included `tests/test_services/test_storage_migration.py` in `42 passed`. | No fresh current product-live run after all release changes proving existing real V2 + Plan-A data migration in app. |
| 2 SCHNITT audio subtab | partial | `docs/superpowers/synthesis/dg001-g-schnitt-gui-live-2026-06-30.md` shows visible SCHNITT workspace tabs including `Audio`, waveform, and DB-backed timeline; current focused regression included `tests/ui/test_schnitt_audio_adapter.py` and `tests/ui/test_schnitt_audio_binder.py` in `42 passed`. | No fresh installed-app/product live click that specifically proves the OTK-021 audio adapter with real migrated stems. |
| 3 Cross-Project-Reuse | open | Current focused regression included service/UI reuse tests in `42 passed`; `otk-021-tier3-32-cross-project-reuse-2026-06-15.md` documents code/tests. | Its own synthesis says no real GUI re-import in two projects was executed. No fresh current product-live two-project import/toast/green-status proof. |
| 4 File-Tracking | open | Current focused regression included `tests/test_services/test_file_tracking.py` in `42 passed`. | No app-live move-file workflow proof. Service test only. |
| 5 Storage-Browser | pass for visible temp-DB path | `scripts/diag/verify_b547_storage_browser_delete_visible.py --timeout-s 20` rerun on 2026-07-02: `ok=true`, row `1 -> 0`, source root `true -> false`; focused storage tests included in `42 passed`. | Proves visible dialog against temporary real DB/storage, not every production project file. |
| 6 Project-Export + Import on VM | pass service-level VM | `docs/superpowers/synthesis/otk021-vm-portability-live-2026-07-02.md`: Windows Sandbox, Project-Bundle verifier `exit_code=0`, `ok=true`. | Service-level VM proof using mapped PB Python runtime, not manual installed-app GUI clicks. |
| 7 Backup + Restore on VM | pass service-level VM | `docs/superpowers/synthesis/otk021-vm-portability-live-2026-07-02.md`: Windows Sandbox, Backup/Restore verifier `exit_code=0`, `ok=true`. | Service-level VM proof using mapped PB Python runtime, not manual installed-app GUI clicks. |

## Commands Run 2026-07-02

```powershell
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe scripts\diag\verify_b547_storage_browser_delete_visible.py --timeout-s 20
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe -m pytest tests\test_services\test_storage_migration.py tests\ui\test_schnitt_audio_adapter.py tests\ui\test_schnitt_audio_binder.py tests\test_services\test_cross_project_reuse.py tests\ui\test_cross_project_reuse.py tests\test_services\test_file_tracking.py tests\test_services\test_storage_browser.py tests\test_ui\test_storage_browser.py tests\test_services\test_b578_rmtree_junction_guard.py -q
```

Result: Storage-Browser visible verifier `ok=true`; focused tests `42 passed in 15.42s`.

## Verdict

OTK-021 90 Live-Verify is not complete. Steps 5, 6, and 7 now have current strong evidence within their stated limits. Steps 1-4 still need product-live verification or an explicit user re-decision that service/regression evidence is sufficient.

No `fixed` marker may be set from this audit.
