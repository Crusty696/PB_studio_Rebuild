---
type: synthesis
title: Full Audit Fixplan Verification Matrix - 2026-05-31
status: code-complete-live-pending
plan_id: PB-STUDIO-FULL-AUDIT-FIXPLAN-2026-05-31
date: 2026-06-01
---

# Full Audit Fixplan Verification Matrix - 2026-05-31

## Scope

Plan: `PB-STUDIO-FULL-AUDIT-FIXPLAN-2026-05-31`

Source audit: `PB-STUDIO-FULL-PROJECT-FILE-AUDIT-2026-05-31`

This matrix records exact verification evidence for FPA-001 through FPA-010. It does not mark user-facing `fixed` status. Several entries are code/test complete but still lack a manual user workflow.

## Matrix

| Finding | Unit test | Integration test | Live test | Vault file | Commit hash | Status |
|---|---|---|---|---|---|---|
| FPA-001 default test gate | `tests/test_ci_policy.py` passed; B-441..B-456 targeted tests passed during follow-up chain. | Default pytest gate passed: `2315 passed, 37 skipped, 6 deselected, 62 warnings in 810.22s`. Not rerun after Task 9. | No app live workflow. | `wiki/synthesis/plan-full-project-audit-fixplan-2026-05-31.md`; B-441..B-456 bug files. | `9782220`, `601b7bb`..`6fa6954` | code-fix-pending-live-verification |
| FPA-002 runtime drift | Active and bare runtime import smokes passed. | Manifest/env comparison documented. | No app live workflow. | `wiki/synthesis/runtime-manifest-drift-2026-05-31.md` | `1aced31` | code-complete-live-pending |
| FPA-003 boot path | Boot contract gate passed: `14 passed in 2.00s`. | Startup check GPU/environment tests included in same gate. | Boot live passed: window opened; log showed `Startup checks completed`; no current-run traceback. | `wiki/synthesis/boot-live-2026-05-31.md` | `6a97f45` | code-fix-pending-live-verification |
| FPA-004 project switch | Project-switch guard tests passed. | Task target plus ingest suite passed: `24 passed in 7.58s`. | No app live project-switch workflow. | `wiki/code/modules/db-project-switch-soft-delete-safety.md` | `69a8097` | code-fix-pending-live-verification |
| FPA-005 soft-delete/orphan | Soft-delete visibility tests passed. | Direct deep DB script passed: `78 PASS / 0 FAIL`; pytest runner for `tests/test_db_deep.py` still reports INTERNALERROR because that standalone script calls `sys.exit(0)` at import. | No app live workflow. | `wiki/code/modules/db-project-switch-soft-delete-safety.md` | `69a8097` | code-fix-pending-live-verification |
| FPA-006 FFmpeg resolver | Resolver regression tests passed. | Video primitive target gate passed: `24 passed in 15.39s`. | No app import/export live workflow. | `wiki/code/modules/video-pipeline-ffmpeg-resolver.md` | `32789df` | code-fix-pending-live-verification |
| FPA-007 LLM/action boundary | Action boundary tests passed: `34 passed in 0.91s`. | Local-agent malformed JSON and destructive-action path covered by target gate. | No live Ollama/tool-click workflow. | `wiki/code/modules/local-agent-action-boundary.md` | `8c422ba` | code-fix-pending-live-verification |
| FPA-008 QThread lifecycle | Lifecycle/dispatcher/task-manager gate passed: `29 passed in 3.16s`. | WorkerDispatcher error cleanup included. | No manual UI workflow. | `wiki/code/modules/qthread-lifecycle-contract.md` | `e6f65f2` | code-fix-pending-live-verification |
| FPA-009 GPU serialization | GPU contract/model gate passed: `14 passed in 35.83s`. | Video model services included SigLIP and RAFT service live_gpu tests. | Pipeline live_gpu gate passed: `3 passed in 38.53s`. | `wiki/synthesis/gpu-serialization-live-2026-05-31.md` | `ac55ec3` | code-fix-pending-live-verification |
| FPA-010 mutating surfaces | Mutating surface guard tests passed: `4 passed in 5.94s`. | VectorDB delete scope and timeline snapshot scope covered in same gate. | No manual app workflow. | `wiki/code/modules/mutating-surface-guards.md` | `9a5483e` | code-fix-pending-live-verification |

## Handoff Fact

Task 10 plan order asks for `agent_handoff` before the matrix commit while also creating a new matrix file. A clean handoff cannot happen while the matrix file is uncommitted. Therefore the clean handoff check must be run after the matrix commit.

## Open

- No `fixed` status written.
- Manual user workflows remain open where matrix rows say no live workflow.
- Full default pytest gate was not rerun after Task 9; Task-specific gates after Task 1 passed as listed.
