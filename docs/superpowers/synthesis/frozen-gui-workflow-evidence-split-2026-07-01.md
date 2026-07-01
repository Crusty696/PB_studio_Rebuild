---
status: frozen-wrapper-pass-after-b586-fix
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

Follow-up fix 2026-07-01:

- Root cause: `main.py` called `faulthandler.enable()` while the windowed
  PyInstaller runtime had `sys.stderr is None`, producing the PyInstaller
  dialog `Failed to execute script 'main' due to unhandled exception:
  sys.stderr is None`.
- `main.py` now falls back to `logs/freeze_stacks.log` for faulthandler when
  stderr is missing.
- `verify_frozen_gui_workflow.py` now selects a Python with GUI verifier deps
  (`pygetwindow`, `pywinauto`, `pyautogui`) via `PB_GUI_VERIFIER_PYTHON`,
  current Python, then the local `pb-studio` Conda runtime.
- Rebuilt `dist\pb_studio\pb_studio.exe` and installer pair.
- Direct `verify_frozen_gui_workflow.py` run passed after rebuild:
  `status=pass`, `window_responsive=true`, `process_alive_after_5s=true`,
  `window_title=PB_studio v0.5.0 — Director's Cockpit`, `uia_label_count=73`,
  screenshot `tests/qa_artifacts/frozen_gui_workflow_20260701_210511.png`,
  `proof_written=false`.
- Focused pytest after the fix: `19 passed`.
- `verify_release_evidence_matrix.py` still reports `release_ready=false`.
- `release_gate.py` still blocks on `DG-001`, `SIGN-001`, `VM-001`, and
  `GUI-001`.

Honest limit: this does not clear `GUI-001`. It proves only the rebuilt
frozen-dist GUI preflight. Installed-app GUI proof is still missing because
`C:\Program Files\PB Studio\pb_studio.exe` does not exist.
