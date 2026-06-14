# PB Studio Deferred Gates

Purpose: hard reminder list for user-approved deferrals. A deferred gate is not
fixed and not forgotten. Before release/fixed status, each gate must be either
live-verified or explicitly re-decided by the user.

## Active Deferred Gates

| gate_id | source_task | status | must_happen_later | reason | evidence |
|---|---|---|---|---|---|
| DG-001 | OTK-019 Video Pipeline Engine | deferred-heavy-live-gate | Run full 4h model-pipeline test on GTX 1060; verify human/QMediaPlayer proxy playback acceptance; run real concurrent Demucs+Video coexistence test. | User chose on 2026-06-14 to plan the heavy 4h gate for later so OTK-021 can proceed. | `test-report/otk019-remaining-2026-06-14/result.json`; Vault `live-verify-video-pipeline-2026-06-11.md`; Decision `D-063-storage-provenance-prereq-waiver.md` |

## Rules

- Deferred gate does not permit `fixed`.
- Deferred gate must be named in any downstream task that depends on it.
- If downstream implementation touches the deferred area, re-check the gate.
- Before release, every active deferred gate needs user decision or live proof.
