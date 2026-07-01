# Installed-App GUI Readiness Preflight 2026-07-01

status: preflight-blocked
plan_id: PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09
task: OTK-021 90 Live-Verify

## Scope

This is not a release-gate proof. It checks whether this machine is ready to
install PB Studio and run the installed-app GUI workflow required for `GUI-001`.

## Commands

```powershell
& "C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe" -m py_compile scripts\diag\verify_installed_app_gui_readiness.py
& "C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe" scripts\diag\verify_installed_app_gui_readiness.py
```

## Result

- `scripts/diag/verify_installed_app_gui_readiness.py`: Exit 0.
- JSON artifact: `tests/qa_artifacts/installed_app_gui_readiness.json`.
- `installed_app_gui_ready=false`.
- Current process is not admin.
- Default installed EXE is missing:
  `C:\Program Files\PB Studio\pb_studio.exe`.
- Installer exists:
  `dist/pb_studio_setup_v0.5.0.exe`, 422,926 bytes.
- NSISBI payload exists:
  `dist/pb_studio_setup_v0.5.0.nsisbin`, 2,815,066,504 bytes.
- Installer policy from `installer/pb_studio.nsi` requires admin,
  defaults to `$PROGRAMFILES64\PB Studio`, and writes HKLM uninstall keys.
- Installer Authenticode status is not signed (`Status=2`).

Blockers:

- `installer-requires-admin-current-process-not-admin`
- `installed-exe-missing`
- `installer-not-signed`

## Honest Limit

This preflight does not install PB Studio, does not click through the installed
app, does not prove clean-VM behavior, and does not clear `GUI-001`.

`GUI-001` remains valid until the installer is run on an installed target and a
full installed-app GUI workflow is recorded in a schema-valid
`release_gate_proof` synthesis with `proof_type: installed-app-gui`,
`status: pass`, and `evidence_level: live`.
