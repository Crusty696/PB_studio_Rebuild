---
status: frozen-gui-pass-release-blocked
plan: PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09
task: OTK-021 90 Live-Verify
date: 2026-07-01
---

# Frozen GUI Workflow Verifier Update

Scope: update GUI workflow verifier after a frozen `dist\pb_studio\pb_studio.exe`
live attempt showed the current UI labels differ from the older verifier
expectations.

Observed failed run:

- EXE launched from `dist\pb_studio\pb_studio.exe`.
- Window appeared and process stayed alive.
- Title included `(Keine Rückmeldung)`.
- Screenshot showed current tabs: `PROJEKT`, `MATERIAL ANALYSE`, `SCHNITT`,
  `EXPORT`.
- Old verifier expected `Projekt Workflow`, `Material und Analyse Workflow`,
  `Schnitt Workflow`, `Export Workflow`.

Verifier update:

- Waits for responsive window title before accepting labels.
- Accepts current navigation labels and legacy workflow labels.
- Reports observed/missing label groups and UIA label count.

Verification:

- `py_compile` passed for verifier and unit test.
- Focused pytest passed: `tests/test_scripts/test_installed_app_gui_workflow.py`
  plus release matrix/cutover tests -> `6 passed`.
- Frozen GUI live rerun against `dist\pb_studio\pb_studio.exe` passed.
- Evidence JSON: `tests/qa_artifacts/installed_app_gui_workflow.json`.
- Screenshot: `tests/qa_artifacts/installed_app_gui_workflow_20260701_171050.png`.
- Observed: `process_alive_after_5s=true`, `window_responsive=true`,
  `uia_label_count=250`, label groups `project`, `material`, `schnitt`,
  `export` present.
- `proof_written=false`.

Honest limit: this does not clear `GUI-001`. `GUI-001` requires installed-app
GUI live proof, not a frozen-dist preflight.
