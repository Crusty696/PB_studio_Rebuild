---
release_gate_proof: true
proof_type: installed-app-gui
status: pass
evidence_level: live
---

# Installed-App GUI Live Proof 2026-07-05

## Scope

This proof was generated only after launching the installed PB Studio EXE and
observing the real GUI window.

## Evidence

- Installed EXE: `C:\Users\David_Lochmann\AppData\Local\PB Studio\pb_studio.exe`
- Installed EXE SHA256: `B56D4EE5DF81E2919E0CC83074900C96EF4A9CCDEA2A953D84ACFEC86B98262E`
- Installer SHA256: `6C2872DEC5D767A1681545B8394C30A841C6E300DAA8F50C22A70A4A05FC2C96`
- NSISBI payload SHA256: `AA3597B339D5F495E3AD45D9D19D94B9BE4CF68AAC7A96C7B7F3E1804805B286`
- PID: `13424`
- Window title: `PB_studio v0.5.0 — Director's Cockpit`
- Screenshot: `C:\Users\David_Lochmann\Documents\PB_studio_Rebuild\PB_studio_Rebuild\tests\qa_artifacts\installed_app_gui_workflow_20260705_003308.png`
- Required labels observed: `Projekt Workflow, Material und Analyse Workflow, Schnitt Workflow, Export Workflow`.

## Limit

This proof only covers installed-app GUI launch/navigation shell readiness. It
does not prove code signing, clean-VM installation, or the DG-001 H1 user
decision.
