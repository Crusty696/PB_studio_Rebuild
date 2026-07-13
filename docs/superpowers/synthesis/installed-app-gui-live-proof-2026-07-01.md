---
release_gate_proof: true
proof_type: installed-app-gui
status: pass
evidence_level: live
---

# Installed-App GUI Live Proof 2026-07-13

## Scope

This proof was generated only after launching the installed PB Studio EXE and
observing the real GUI window.

## Evidence

- Installed EXE: `C:\Users\David_Lochmann\AppData\Local\PB Studio\pb_studio.exe`
- Installed EXE SHA256: `2005BE2026FAEDFE50280B74F41D40B9D9C7DFEDC7BD7A6F2BE6A52D9A12119E`
- Installer SHA256: `EAC4B9DB96BEAF52538603F63E9E4E543B2DE7B52FD6427ABBB2307AC325DF2F`
- NSISBI payload SHA256: `FF1A80ACD3ADC91A23E87B10EF209D6BCEBED288BEB63091392A23877757F76D`
- PID: `1256`
- Window title: `PB_studio v0.5.0 — Director's Cockpit`
- Screenshot: `C:\Users\David_Lochmann\Documents\PB_studio_Rebuild\PB_studio_Rebuild\tests\qa_artifacts\installed_app_gui_workflow_20260713_073746.png`
- Required labels observed: `Projekt Workflow, Material und Analyse Workflow, Schnitt Workflow, Export Workflow`.

## Limit

This proof only covers installed-app GUI launch/navigation shell readiness. It
does not prove code signing, clean-VM installation, or the DG-001 H1 user
decision.
