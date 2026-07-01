# Installed-App GUI Workflow Verifier 2026-07-01

status: verifier-ready-currently-blocked
plan_id: PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09
task: OTK-021 90 Live-Verify

## Scope

`scripts/diag/verify_installed_app_gui_workflow.py` launches the installed
PB Studio executable, waits for a real visible GUI window, records a cropped
screenshot, checks the four workflow tabs via UIA, and writes a schema-valid
`release_gate_proof` synthesis only when the installed-app GUI run passes and
`--write-proof` is explicitly used.

## Commands

```powershell
& "C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe" -m py_compile scripts\diag\verify_installed_app_gui_workflow.py
& "C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe" scripts\diag\verify_installed_app_gui_workflow.py
```

## Current Result

- `scripts/diag/verify_installed_app_gui_workflow.py`: blocked with exit 2.
- JSON artifact: `tests/qa_artifacts/installed_app_gui_workflow.json`.
- `installed_app_gui_workflow_passed=false`.
- `proof_written=false`.
- Blocker: `installed-exe-missing`.
- Missing installed executable:
  `C:\Program Files\PB Studio\pb_studio.exe`.

## Honest Limit

This verifier cannot pass on a machine where
`C:\Program Files\PB Studio\pb_studio.exe` does not exist. It does not install
PB Studio, does not sign the installer, and does not prove clean-VM behavior.

`GUI-001` remains valid.
