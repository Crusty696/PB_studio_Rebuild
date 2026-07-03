---
status: product-path-pass-open
task: OTK-021 90 Live-Verify current audit
date: 2026-07-04
head: 29aaf37
fixed_marker_allowed: false
---

# OTK-021 90 Live-Verify Current Audit - 2026-07-04

## Task Quote

Source: `docs/superpowers/archive/2026-05-19-global-storage-provenance/90_LIVE_VERIFY.md`

1. Migration: existing V2 + Plan-A data registered into `by_sha/` via junctions.
2. SCHNITT audio subtab still works without code touch.
3. Cross-Project-Reuse: same file in two projects -> notify toast, analyses immediately green.
4. File-Tracking: moved file -> app finds it again via SHA.
5. Storage-Browser: all files visible, bulk delete works.
6. Project-Export + Import on another VM.
7. Backup + Restore on VM.

Acceptance: all seven steps without stacktrace, SCHNITT functional, V2 pipeline
still writes provenance. Only then `fixed`.

## Current Verdict

OTK-021 now has current evidence for all seven mandatory steps, but the evidence
is not identical in strength:

| Step | Current status | Evidence | Honest limit |
|---|---|---|---|
| 1 Migration | product-path pass | `verify_otk021_migration_schnitt_audio_product_path.py` on HEAD `29aaf37`: `status=pass`; V2 stems and Plan-A outputs registered into `by_sha`, stem link is reparse/junction, ProjectSource/jobs/artifacts/manifests green. | Product-path/offscreen proof, not manual installed-app GUI click. |
| 2 SCHNITT audio subtab | product-path pass | Same verifier: real `SchnittTabAudio` + `SchnittAudioBinder`, `4/4 Stems`, LUFS, key, waveform scene, screenshot saved. | Offscreen widget proof; screenshot text has square glyphs, machine label checks are green. |
| 3 Cross-Project-Reuse | product-path pass | `verify_otk021_cross_project_reuse_import_notify.py` on HEAD `29aaf37`: Project A/B import, `AnalysisStatus stem_separation=done`, reused stems exist, notify message + non-modal notice. | No manual import-dialog click. |
| 4 File-Tracking | product-path pass | `verify_otk021_file_tracking_open_project.py` on HEAD `29aaf37`: `ProjectManager.open_project()` repairs stale ProjectSource path to moved file by SHA. | No manual GUI open-project click. |
| 5 Storage-Browser | visible-dialog pass | `verify_b547_storage_browser_delete_visible.py --timeout-s 20` on HEAD `29aaf37`: `ok=true`, row `1 -> 0`, source root `true -> false`, confirm/result dialogs captured. | Temp DB/storage proof, not every production project file. |
| 6 Project-Export + Import on VM | service-level VM pass | `otk021_vm_portability_probe.json` from Windows Sandbox 2026-07-02: Project-Bundle `exit_code=0`, `ok=true`. Release gate on HEAD still OK. | Service-level VM proof using mapped PB Python runtime, not manual installed-app GUI click. |
| 7 Backup + Restore on VM | service-level VM pass | Same Windows Sandbox proof: Backup/Restore `exit_code=0`, `ok=true`. Release gate on HEAD still OK. | Service-level VM proof using mapped PB Python runtime, not manual installed-app GUI click. |

No `fixed` marker is set. User confirmation is still required for any `fixed`
status marker, and any demand for installed-app/manual GUI proof would require
additional GUI runs.

## Commands Run On 2026-07-04

```powershell
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe scripts\diag\verify_otk021_migration_schnitt_audio_product_path.py
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe scripts\diag\verify_otk021_cross_project_reuse_import_notify.py
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe scripts\diag\verify_otk021_file_tracking_open_project.py
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe scripts\diag\verify_b547_storage_browser_delete_visible.py --timeout-s 20
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe -m pytest tests\test_services\test_storage_migration.py tests\ui\test_schnitt_audio_adapter.py tests\ui\test_schnitt_audio_binder.py tests\test_services\test_cross_project_reuse.py tests\ui\test_cross_project_reuse.py tests\test_services\test_file_tracking.py tests\test_services\test_storage_browser.py tests\test_ui\test_storage_browser.py tests\test_services\test_b578_rmtree_junction_guard.py -q --basetemp tests\qa_artifacts\pytest-otk021-current-steps1-5
C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe tools\release_gate.py
```

Results:

- Step 1-2 verifier: exit 0, `status=pass`.
- Step 3 verifier: exit 0, `status=pass`.
- Step 4 verifier: exit 0, `status=pass`.
- Step 5 verifier: exit 0, `ok=true`.
- Focused OTK-021 steps 1-5 regression: `43 passed in 16.92s`.
- Release gate: `RELEASE-GATE OK: keine offenen Deferred Gates oder Produktionsblocker.`

## Evidence Artifacts

- `tests/qa_artifacts/otk021_migration_schnitt_audio_product_path_result.json`
- `tests/qa_artifacts/otk021_migration_schnitt_audio_product_path_schnitt_audio.png`
- `tests/qa_artifacts/otk021_cross_project_reuse_import_notify_result.json`
- `tests/qa_artifacts/otk021_file_tracking_open_project_result.json`
- `tests/qa_artifacts/b547_storage_browser_delete_visible_result.json`
- `tests/qa_artifacts/otk021_vm_portability_probe.json`

## Honest Open Items

- No human/manual installed-app click-through was executed for steps 1-4.
- Step 5 proves the visible dialog against a real temporary DB/storage, not every
  production project.
- Steps 6-7 are Windows Sandbox service-level proofs, not installed-app GUI
  proofs inside the guest.
- `29aaf37` is an Antigravity timeline commit with body
  `(unverified -- pending user test)`; it is pushed and preserved, but this
  audit did not verify B-553.

## Conclusion

OTK-021 90 Live-Verify has a current product-path/service-level PASS matrix for
all seven mandatory steps within the limits above. It is not truthfully
claimable as fully manual installed-app GUI verified. No `fixed` marker may be
set by the agent without explicit user confirmation.
