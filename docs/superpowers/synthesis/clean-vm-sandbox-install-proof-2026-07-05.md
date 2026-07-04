---
release_gate_proof: true
proof_type: clean-vm-install
status: pass
evidence_level: live
---

# Clean VM Install Proof - Windows Sandbox - 2026-07-05

## Evidence

- Environment: Windows Sandbox / clean ephemeral Windows user WDAGUtilityAccount on D6A2407A-0043-4.
- OS: Microsoft Windows 10 Enterprise 10.0.19041 build 19041.
- Installer: C:\Users\WDAGUtilityAccount\Desktop\PBStudioRelease\dist\pb_studio_setup_v0.5.0.exe
- Installer SHA256: 6C2872DEC5D767A1681545B8394C30A841C6E300DAA8F50C22A70A4A05FC2C96
- Payload: C:\Users\WDAGUtilityAccount\Desktop\PBStudioRelease\dist\pb_studio_setup_v0.5.0.nsisbin
- Payload SHA256: AA3597B339D5F495E3AD45D9D19D94B9BE4CF68AAC7A96C7B7F3E1804805B286
- Installed EXE: C:\Users\WDAGUtilityAccount\AppData\Local\PB Studio\pb_studio.exe
- Registry key: HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\PBStudio
- App launch: process started successfully in sandbox.
- JSON proof: C:\Users\WDAGUtilityAccount\Desktop\PBStudioRelease\tests\qa_artifacts\clean_vm_sandbox_probe.json

## Limit

This proof covers a clean Windows Sandbox install and launch. It does not prove public publisher trust; the installer uses the self-signed certificate approved for the free app path.
