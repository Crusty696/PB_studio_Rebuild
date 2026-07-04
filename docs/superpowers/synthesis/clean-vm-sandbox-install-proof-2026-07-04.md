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
- Installer SHA256: 1BB5F755C805437D9EDDDA5E2A31FFAD52B0FEB0BCF94C0D1A8FD31B90C9B758
- Payload: C:\Users\WDAGUtilityAccount\Desktop\PBStudioRelease\dist\pb_studio_setup_v0.5.0.nsisbin
- Payload SHA256: 8E15A1876216369F2F48FC83027A53993F74A6BDCF337BAB59541FEE4F36B4C9
- Installed EXE: C:\Users\WDAGUtilityAccount\AppData\Local\PB Studio\pb_studio.exe
- Registry key: HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\PBStudio
- App launch: process started successfully in sandbox.
- JSON proof: C:\Users\WDAGUtilityAccount\Desktop\PBStudioRelease\tests\qa_artifacts\clean_vm_sandbox_probe.json

## Limit

This proof covers a clean Windows Sandbox install and launch. It does not prove public publisher trust; the installer uses the self-signed certificate approved for the free app path.
