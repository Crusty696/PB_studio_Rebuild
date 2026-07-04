---
release_gate_proof: true
proof_type: clean-vm-install
status: pass
evidence_level: live
---

# Clean VM Install Proof - Windows Sandbox - 2026-07-04

## Evidence

- Environment: Windows Sandbox / clean ephemeral Windows user WDAGUtilityAccount on D6A2407A-0043-4.
- OS: Microsoft Windows 10 Enterprise 10.0.19041 build 19041.
- Installer: C:\Users\WDAGUtilityAccount\Desktop\PBStudioRelease\dist\pb_studio_setup_v0.5.0.exe
- Installer SHA256: 722E6EED2D15CB44903DDDC8106998F32C2FF29FD8A84BB7A65A4F7F5E901D50
- Payload: C:\Users\WDAGUtilityAccount\Desktop\PBStudioRelease\dist\pb_studio_setup_v0.5.0.nsisbin
- Payload SHA256: 2BA8F99B4F9EDA9222A589BE9861C3F8500EB731395D969903BB577CDF2FF7A9
- Installed EXE: C:\Users\WDAGUtilityAccount\AppData\Local\PB Studio\pb_studio.exe
- Registry key: HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\PBStudio
- App launch: process started successfully in sandbox.
- JSON proof: C:\Users\WDAGUtilityAccount\Desktop\PBStudioRelease\tests\qa_artifacts\clean_vm_sandbox_probe.json

## Limit

This proof covers a clean Windows Sandbox install and launch. It does not prove public publisher trust; the installer uses the self-signed certificate approved for the free app path.
