# Full Project Conflict Quality Audit - Bottom-Up Pass 2026-06-07

plan_id: PB-STUDIO-CONFLICT-QUALITY-AUDIT-2026-06-07
task: Task 3 Bottom-Up Audit
status: static-complete
mode: audit-plan
created: 2026-06-07

## Task Quote

```text
Audit from tests, imports, symbols, call sites, failure branches, cleanup paths, cancellation paths, rollback paths, dead-code candidates, inactive UI wiring, and user workflow edges using a route independent from Task 2.
```

## Evidence Commands

```powershell
git status --short --branch
conda run -n pb-studio pytest --collect-only -q
& "$env:USERPROFILE\miniconda3\Scripts\conda.exe" run -n pb-studio pytest --collect-only -q
rg -n "connect\(|triggered\.connect|clicked\.connect|emit\(|delete_selected|delete_all|restore|rollback|cancel|cleanup|finally|except Exception" ui services workers agents tests --glob "*.py"
rg -n "test_.*(cancel|rollback|restore|delete|soft|thread|worker|pipeline|status|ffmpeg|ollama|cuda|gpu|timeline|schnitt)" tests --glob "*.py"
```

## Test Collection

Observed:

- Plain `conda run -n pb-studio pytest --collect-only -q` failed because `conda` is not in PATH in this shell.
- `%USERPROFILE%\miniconda3\Scripts\conda.exe` exists.
- `%USERPROFILE%\miniconda3\envs\pb-studio\python.exe` exists.
- Absolute Conda command succeeded.
- `pytest --collect-only -q`: 2420 tests collected in 62.55s.
- Collection warning: `tests\test_audio_analysis_real.py:46` class `TestResult` cannot be collected because it has `__init__`.

## Bottom-Up Coverage Counts

| Evidence route | Observed count |
|---|---:|
| Signal/wiring hits (`connect`, `emit`, `clicked`, `triggered`) | 1244 |
| Failure/cancel/cleanup/rollback/delete hits | 2036 |
| Test-name hits for cancel/rollback/restore/delete/soft/thread/worker/pipeline/status/ffmpeg/ollama/cuda/gpu/timeline/schnitt | 462 |
| Total tests collected | 2420 |

These counts prove broad test and call-site surface exists. They do not prove each workflow is live-verified.

## Independent Findings

| ID | Severity | Category | Evidence | Observed fact | Impact | Verification |
|---|---|---|---|---|---|---|
| BU-001 | medium | test command portability | Failed command output: `conda: The term 'conda' is not recognized`; `docs/superpowers/AGENT_HANDOFF.md:102` tells Codex to run `conda run -n pb-studio ...`; `README.md:204` documents absolute env Python alternative. | Handoff test command is not executable in current shell unless Conda is on PATH. Absolute Miniconda path works. | Next agent can falsely think tests are blocked or fail before using the valid env path. | command evidence |
| BU-002 | low | test collection hygiene | collect-only warning; `tests/test_audio_analysis_real.py:46` defines `class TestResult`. | Pytest tries to collect helper class named `TestResult` and warns because it has `__init__`. | Noise in collection; can hide future real warnings in long output. | collect-only evidence |
| BU-003 | medium | dead-code candidate | AST/text heuristic: 75 public top-level definitions in `services/`, `ui/`, `workers/`, `agents/` had only one source occurrence. Repo-wide check showed `ui/workspaces/workflow_pages.py:383` `LegacyAnalysisWorkspace` and `:586` `set_tab_if_available` only as definitions; old audit `docs/AUDIT_REPORT_2026-05-01.md:123-128` already called `LegacyAnalysisWorkspace` dead code. | Some legacy UI code remains present with no current source call site. | Maintenance cost and false architecture map. Needs reviewer challenge before deletion. | static candidate, not proof |
| BU-004 | low | inactive widget candidate | `ui/widgets/analysis_status_panel.py:617` `AnalysisStatusMiniWidget` appears only as class definition in repo-wide source search. | Mini status widget may be unused. | Small cleanup candidate; not a runtime blocker. Needs import/runtime check before action. | static candidate, not proof |
| BU-005 | informational | removed-feature guard present | `tests/ui/test_media_workspace_layout.py:16-27`; `tests/ui/test_checkbox_workflow_smoke.py:49-62`; `tests/ui/test_workspaces_smoke.py:207-258`. | Tests assert removed aliases `btn_motion_analysis` and `btn_siglip_embeddings` do not return. | Good guard: prior inactive/duplicate UI functions have regression coverage. | static test evidence |

## Dead-Code Candidate Notes

The 75-candidate heuristic is intentionally conservative and noisy:

- It excludes private names, but dynamic registry actions and plugin-style entrypoints still appear as false positives.
- Examples likely false-positive: action functions in `services/actions/*`, test reset helpers, public service APIs.
- Examples needing reviewer challenge: `LegacyAnalysisWorkspace`, `set_tab_if_available`, `AnalysisStatusMiniWidget`.

No code deletion is authorized by this audit pass.

## Workflow Edge Evidence

Observed tests directly cover:

- destructive action boundary: `tests/test_agents/test_local_agent_action_boundary.py`
- QThread lifecycle/cancel: `tests/test_services/test_qthread_lifecycle_contract.py`
- pipeline cancel status: `tests/test_services/test_pipeline_cancel_marks_status.py`
- timeline snapshot restore: `tests/test_services/test_timeline_snapshot_service.py`
- soft-delete guards: `tests/test_services/test_soft_delete_visibility.py`, `tests/test_services/test_b369_video_soft_delete_guards.py`
- Schnitt controller/UI wiring: `tests/ui/test_schnitt_controller_wiring.py`, `tests/ui/test_schnitt_integration_boot.py`
- worker cleanup: `tests/ui/test_worker_dispatcher_error_cleanup.py`

This is static/collection evidence only. It is not live proof.

## Not Checked In Task 3

- No tests executed beyond collection.
- No imports executed beyond pytest collection.
- No UI clicked.
- No source code edited.
- No dead-code candidate removed.

## Verification Status

Bottom-up static pass complete. `pytest --collect-only` succeeded with absolute Conda path. No app code changed. No live verification performed. No finding marked fixed.
