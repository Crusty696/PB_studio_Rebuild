---
release_gate_proof: true
proof_type: installed-app-gui
status: pass
evidence_level: live
---

# Installed-App GUI Live Proof 2026-07-04

## Scope

This proof was generated only after launching the installed PB Studio EXE and
observing the real GUI window.

## Evidence

- Installed EXE: `C:\Users\David_Lochmann\AppData\Local\PB Studio\pb_studio.exe`
- Installed EXE SHA256: `5EDD2D1AAF7B556900C65E4EE577B6EBB2D89476C900609EF7C3BE210F3A5D4E`
- Installer SHA256: `722E6EED2D15CB44903DDDC8106998F32C2FF29FD8A84BB7A65A4F7F5E901D50`
- NSISBI payload SHA256: `2BA8F99B4F9EDA9222A589BE9861C3F8500EB731395D969903BB577CDF2FF7A9`
- PID: `13568`
- Window title: `PB_studio v0.5.0 — Director's Cockpit`
- Screenshot: `C:\Users\David_Lochmann\Documents\PB_studio_Rebuild\PB_studio_Rebuild\tests\qa_artifacts\installed_app_gui_workflow_20260704_fresh_20260704_214807.png`
- Required labels observed: `Projekt Workflow, Material und Analyse Workflow, Schnitt Workflow, Export Workflow`.

## Limit

This proof only covers installed-app GUI launch/navigation shell readiness. It
does not prove code signing, clean-VM installation, or the DG-001 H1 user
decision.
