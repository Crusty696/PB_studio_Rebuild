---
status: blocked
plan: PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09
task: OTK-021 90 Live-Verify
date: 2026-07-01
blocker: GUI-001
---

# Installed-App Silent Install Attempt 2026-07-01

Scope: test whether the current local installer can be installed silently from
the current non-admin agent process so `GUI-001` can move to an installed-app
GUI proof.

Command:

```powershell
Start-Process -FilePath dist\pb_studio_setup_v0.5.0.exe -ArgumentList '/S' -Wait -PassThru -NoNewWindow
```

Result:

- PowerShell/Start-Process failed:
  `This command cannot be run due to the error: Der angeforderte Vorgang erfordert erhöhte Rechte.`
- `C:\Program Files\PB Studio\pb_studio.exe` still does not exist.
- `scripts/diag/verify_installed_app_gui_readiness.py` still reports:
  `installer-requires-admin-current-process-not-admin`,
  `installed-exe-missing`, `installed-app-registry-entry-missing`,
  `installer-not-signed`.
- `scripts/diag/verify_installed_app_gui_workflow.py` still reports:
  `status=blocked`, `installed-exe-missing`, `proof_written=false`.

Evidence artifacts:

- `tests/qa_artifacts/installed_app_silent_install_attempt_stdout.txt`
- `tests/qa_artifacts/installed_app_silent_install_attempt_stderr.txt`
- `tests/qa_artifacts/installed_app_gui_readiness.json`
- `tests/qa_artifacts/installed_app_gui_workflow.json`

Honest limit: this does not install PB Studio and cannot clear `GUI-001`. A
real installed-app GUI proof still requires admin/elevated installation or an
explicit installer-policy change approved by the user.
