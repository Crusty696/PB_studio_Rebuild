---
status: blocked
plan: PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09
task: OTK-021 90 Live-Verify
date: 2026-07-01
---

# Installed-App GUI Readiness Install Detection

Scope: improve installed-app GUI readiness evidence by checking more than the
default installed EXE path.

Updated verifier: `scripts/diag/verify_installed_app_gui_readiness.py`.

Output artifact: `tests/qa_artifacts/installed_app_gui_readiness.json`.

Changes:

- Reports installed EXE candidates from Program Files, Program Files (x86),
  LocalAppData, and `PB_INSTALLED_EXE`.
- Queries uninstall registry entries in HKLM 64-bit, HKLM WOW6432Node, and HKCU.
- Keeps `installed_app_gui_ready=false` when no installed EXE/registry entry is
  present or installer remains unsigned.

Honest limit: this preflight does not install PB Studio, launch the installed
GUI, write release proof frontmatter, or clear `GUI-001`.
