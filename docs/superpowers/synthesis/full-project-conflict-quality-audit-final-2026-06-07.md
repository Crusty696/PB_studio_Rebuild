# Full Project Conflict Quality Audit - Final Report 2026-06-07

plan_id: PB-STUDIO-CONFLICT-QUALITY-AUDIT-2026-06-07
task: Task 5 Final Audit Report And Fix-Plan Candidate
status: static-complete
mode: audit-plan
created: 2026-06-07

## Scope

Read-only whole-project audit for conflicts, bugs, gaps, errors, false assumptions, dead code, inactive functions, blockers, and stability/performance/quality improvements.

Included:

- 1187 tracked repo files inventory-classified.
- 1451 ignored paths classified as excluded unless targeted evidence requires them.
- Governance, active plan, registry, handoff, launch/runtime manifests, CI, DB, worker, UI, FFmpeg, GPU/model, known bug status.
- Test collection and bottom-up call-site/test-surface searches.

Excluded:

- `.git/`, cache dirs, local envs, generated outputs, binary media, logs, model weights, runtime DB files, `.env`.
- App-code edits, fixes, refactors, dependency swaps, and `fixed` status changes.

## Evidence Artifacts

- Inventory: `docs/superpowers/synthesis/full-project-conflict-quality-audit-inventory-2026-06-07.md`
- Tracked TSV: `docs/superpowers/synthesis/full-project-conflict-quality-audit-inventory-files-2026-06-07.tsv`
- Ignored TSV: `docs/superpowers/synthesis/full-project-conflict-quality-audit-ignored-files-2026-06-07.tsv`
- Top-down pass: `docs/superpowers/synthesis/full-project-conflict-quality-audit-topdown-2026-06-07.md`
- Bottom-up pass: `docs/superpowers/synthesis/full-project-conflict-quality-audit-bottomup-2026-06-07.md`
- Reviewer challenge: `docs/superpowers/synthesis/full-project-conflict-quality-audit-reviewer-challenge-2026-06-07.md`
- Vault mirrors exist under `C:\Brain-Bug\projects\pb-studio\wiki\synthesis\`.

## Pass Summaries

Top-down found governance/handoff drift, runtime-manifest drift risk, FFmpeg resolver bypasses, known-bug status drift, and UI performance debt.

Bottom-up found test command portability drift, one pytest collection warning, dead-code/inactive-widget candidates, and confirmed broad static coverage for signal wiring, cancel/cleanup paths, destructive-action boundaries, soft-delete, worker lifecycle, and Schnitt wiring.

Reviewer challenge kept all findings, downgraded CQ-004 from high to medium and BU-003 from medium to low, and corrected language to avoid live-verification overclaim.

## Findings

| ID | Severity | Type | Evidence | Finding | Fix-plan candidate |
|---|---|---|---|---|---|
| CQ-001 | high | governance conflict | `ACTIVE_PLAN.md:4-5`; `AGENT_HANDOFF.md:31`, `:39`, `:97-103` | Active plan is new audit, but handoff still points to old full-audit-fixplan/default-gate. | Sync handoff after user approves maintenance task. |
| CQ-002 | medium | handoff/isolation risk | `git status --short --branch` | Branch name still references old fixplan while active plan is new audit. | Decide whether to keep branch or create/switch to `codex/PB-STUDIO-CONFLICT-QUALITY-AUDIT-2026-06-07`. |
| CQ-003 | medium | runtime drift risk | `poetry.lock:3098-3110`; `requirements-py310-cu113.txt:1-10`; `environment.yml:1-31` | Poetry lock contains cu118/torch 2.4.1 graph; active runtime is cu113/torch 1.12.1. | Mark Poetry lock legacy or regenerate/remove only under explicit dependency-governance task. |
| CQ-004 | medium | FFmpeg resolver bypass | `workers/video.py:634-643`; `ui/widgets/media_grid.py:151-155` | Thumbnail paths call bare `"ffmpeg"` instead of central resolver. | Add resolver tests, then switch to `services.startup_checks.get_ffmpeg_bin()`. |
| CQ-005 | medium | FFprobe resolver bypass | `services/ingest_service.py:124-127`, `:231-240` | Ingest probe path uses env fallback bare `"ffprobe"`/`"ffmpeg"` instead of central resolver. | Add resolver regression test, then use central resolver. |
| CQ-006 | medium | vault status drift | `B-470...md:5`; `log.md:247-249`, `:239`, `:224` | B-470 status text still says root cause needs live stack while log documents Stack-A progress. | Reconcile B-470 bug file without setting `fixed` unless user confirms. |
| CQ-007 | low | optimization candidate | `rg` count 414 table/style/thread hits; QTableWidget sites listed in top-down report | Many per-widget style/table-widget paths remain. | Profile before changing; convert hotspots only. |
| BU-001 | medium | test command portability | failed `conda run`; `AGENT_HANDOFF.md:102`; `README.md:204` | `conda` is not in PATH; absolute Miniconda path works. | Update handoff/test docs to use absolute env Python or resolved Conda path. |
| BU-002 | low | test hygiene | collect-only warning; `tests/test_audio_analysis_real.py:46` | `class TestResult` triggers PytestCollectionWarning. | Rename helper or set `__test__ = False`. |
| BU-003 | low | dead-code candidate | AST/text heuristic; `ui/workspaces/workflow_pages.py:383`, `:586`; old audit `docs/AUDIT_REPORT_2026-05-01.md:123-128` | `LegacyAnalysisWorkspace` and `set_tab_if_available` appear unused. | Confirm with imports/tests, then remove in cleanup task. |
| BU-004 | low | inactive widget candidate | `ui/widgets/analysis_status_panel.py:617` | `AnalysisStatusMiniWidget` appears source-unused. | Confirm not dynamically imported, then remove or wire. |
| BU-005 | informational | guard present | UI tests listed in bottom-up report | Removed aliases `btn_motion_analysis` / `btn_siglip_embeddings` are guarded by tests. | Keep guard. |

## Dependency / Runtime Table

| Area | Status |
|---|---|
| Active install path | `environment.yml` -> `requirements-py310-cu113.txt`, Python 3.10, torch 1.12.1+cu113. |
| CI unit path | Windows Python 3.10, installs `requirements-py310-cu113.txt`. |
| Legacy/future requirements | `requirements.txt` clearly documents Python 3.11+cu124 legacy/future path. |
| Poetry lock | Drift risk: cu118/torch2 graph remains in repo. |
| Conda command availability | Env exists; `conda` command not on PATH in current shell. |

## Verification Matrix

| Check | Result | Verification level |
|---|---|---|
| Governance activation | Done, committed | static/file evidence |
| Inventory | 1187 tracked, 1451 ignored classified | static/command evidence |
| Top-down audit | CQ-001..CQ-007 documented | static/read-only |
| Bottom-up audit | BU-001..BU-005 documented; 2420 tests collected | static/collect-only |
| Reviewer challenge | all findings challenged; severities corrected | static/review |
| App live test | not run | not verified |
| Unit test execution | not run; collection only | not verified |
| Fixes | none authorized, none made | not applicable |

## Fix-Plan Candidate

1. Governance/handoff cleanup: CQ-001, CQ-002, BU-001.
2. FFmpeg resolver cleanup: CQ-004, CQ-005.
3. Runtime-manifest cleanup: CQ-003.
4. Vault status reconciliation: CQ-006 plus known open live-verification statuses B-458/B-459/B-460/B-462/B-463/B-471.
5. Test hygiene cleanup: BU-002.
6. Dead-code/inactive-widget review: BU-003, BU-004.
7. UI performance profiling before any broad UI refactor: CQ-007.

This is a candidate only. It is not implementation authorization.

## Open Questions

- Soll der nächste Plan zuerst Governance/Handoff-Drift beheben oder direkt FFmpeg-Resolver-Fixes planen?
- Soll der Audit-Zweig umbenannt/neuer Branch erstellt werden, oder bleiben Audit-Commits bewusst auf altem Branch?
- Soll `poetry.lock` als legacy markiert, regeneriert, oder entfernt werden?

## Not Checked

- No live GUI workflow.
- No full unit test execution.
- No runtime import smoke.
- No package install.
- No model load.
- No GPU live path.
- No destructive action path.
- No `.env` content.
- No ignored runtime logs beyond path classification.

## Final Status

Audit static-complete. No app code changed. No live verification performed. No `fixed` markers changed.
