---
release_gate_proof: true
proof_type: installed-app-gui
status: pass
evidence_level: live
---

# Installed-App GUI Live Proof 2026-07-09

## Scope

This proof was generated only after launching the installed PB Studio EXE and
observing the real GUI window.

## Evidence

- Installed EXE: `C:\Users\David_Lochmann\AppData\Local\PB Studio\pb_studio.exe`
- Installed EXE SHA256: `78A9C7A7CA165DA3CFB6228864CBAC1D6EC35BBDCCBA635CF92B1D87C91F2098`
- Installer SHA256: `715FE54A5A60AEA40095CEC43097D4A35D589D4D8FD042C6DC880816D109F582`
- NSISBI payload SHA256: `F314757A7A8010DE9667CF581F135AB45E892675726F68AE1DE9693B04D50524`
- PID: `13992`
- Window title: `PB_studio v0.5.0 — Director's Cockpit`
- Screenshot: `C:\Users\David_Lochmann\Documents\PB_studio_Rebuild\PB_studio_Rebuild\.worktrees\vollintegration\tests\qa_artifacts\installed_app_gui_workflow_20260709_171915.png`
- Required labels observed: `Projekt Workflow, Material und Analyse Workflow, Schnitt Workflow, Export Workflow`.

## Limit

This proof only covers installed-app GUI launch/navigation shell readiness. It
does not prove code signing, clean-VM installation, or the DG-001 H1 user
decision.
