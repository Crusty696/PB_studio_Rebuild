---
status: frozen-wrapper-fail
plan: PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09
task: OTK-021 90 Live-Verify
date: 2026-07-01
---

# Frozen GUI Workflow Evidence Split

Scope: keep frozen-dist GUI evidence separate from installed-app GUI release
proof evidence.

Problem: the frozen GUI preflight can launch `dist\pb_studio\pb_studio.exe`,
but `GUI-001` requires proof from the installed app. Writing frozen evidence to
`installed_app_gui_workflow.json` risks confusing later release-gate analysis.

Changes:

- `verify_installed_app_gui_workflow.py` accepts `--output` and
  `--artifact-label`.
- New wrapper `scripts/diag/verify_frozen_gui_workflow.py` targets
  `dist\pb_studio\pb_studio.exe`.
- Frozen evidence writes to `tests/qa_artifacts/frozen_gui_workflow.json`.
- The frozen wrapper never passes `--write-proof`.

Verification:

- `py_compile` passed for workflow verifier, frozen wrapper, and tests.
- Focused pytest passed: installed/frozen GUI workflow tests plus release
  evidence/cutover tests -> `9 passed`.
- Direct `verify_frozen_gui_workflow.py` run failed after the split:
  `status=fail`, `window=null`, `process_alive_after_5s=false`,
  `window_process_id=null`, `uia_label_count=0`.
- No `pb_studio` process remained after the run.
- Output: `tests/qa_artifacts/frozen_gui_workflow.json`.
- Default installed-app workflow was rerun afterward and now writes the honest
  installed-app state: `status=blocked`, `installed-exe-missing`,
  `proof_written=false`.
- `verify_release_evidence_matrix.py` now includes `frozen_gui_workflow`
  separately from `installed_app_gui_workflow`.

Bug:

- `B-586-frozen-gui-wrapper-no-window` tracks the current frozen wrapper fail.

Honest limit: this split does not clear `GUI-001`. It protects evidence
integrity while keeping installed-app proof strict. It also revealed that the
frozen GUI wrapper is not currently a stable passing proof path.
