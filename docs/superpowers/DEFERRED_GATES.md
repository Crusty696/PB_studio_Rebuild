# PB Studio Deferred Gates

Purpose: hard reminder list for user-approved deferrals. A deferred gate is not
fixed and not forgotten. Before release/fixed status, each gate must be either
live-verified or explicitly re-decided by the user.

## Active Deferred Gates

| gate_id | source_task | status | must_happen_later | reason | evidence |
|---|---|---|---|---|---|
| DG-001 | OTK-019 Video Pipeline Engine | deferred-heavy-live-gate | Remaining before release/fixed: obtain human/QMediaPlayer proxy playback acceptance. Already passed: H1 62-min scale run (`H1_EXIT 0`, `failed=False`), H1.3 4h low-profile model-pipeline run on GTX 1060 (`completed_count=7`, `failed_count=0`), H2.1 NVENC export, H3 real concurrent Demucs+Video, SCHNITT GUI widget acceptance. | User chose on 2026-06-14 to plan the heavy 4h gate for later so OTK-021 can proceed. H1.3 agent-run completed on 2026-06-15; H2.2 remains user-only. | `outputs/h1_scale.log`; `C:\PB_Studio_H1_3\pipeline_result.json`; `C:\PB_Studio_H1_3\output_4h.mp4`; `test-report/e2e-live-acceptance-20260615/RESULT.md`; `test-report/e2e-live-acceptance-20260615/exports/phase4_export.mp4`; `test-report/e2e-h3-concurrency-20260615`; `docs/superpowers/DG-001_LIVE_VERIFY.md`; Decision `D-063-storage-provenance-prereq-waiver.md` |

## Rules

- Deferred gate does not permit `fixed`.
- Deferred gate must be named in any downstream task that depends on it.
- If downstream implementation touches the deferred area, re-check the gate.
- Before release, every active deferred gate needs user decision or live proof.
