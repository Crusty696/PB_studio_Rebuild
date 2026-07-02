---
release_gate_proof: false
proof_type: otk021-vm-portability
status: pass
evidence_level: live
date: 2026-07-02
---

# OTK-021 VM Portability Live Proof - 2026-07-02

## Scope

OTK-021 90 Live-Verify steps 6 and 7:

- Project-Export + Import on another VM.
- Backup + Restore on VM.

## Evidence

- Environment: Windows Sandbox / ephemeral Windows user WDAGUtilityAccount on 076C135C-A45C-4.
- OS: Microsoft Windows 10 Enterprise 10.0.19041 build 19041.
- Project bundle verifier: pass.
- Backup/restore verifier: pass.
- JSON proof: C:\Users\WDAGUtilityAccount\Desktop\PBStudioRelease\tests\qa_artifacts\otk021_vm_portability_probe.json
- Project bundle JSON: C:\Users\WDAGUtilityAccount\Desktop\PBStudioRelease\tests\qa_artifacts\otk021_project_bundle_roundtrip_result.json
- Backup/restore JSON: C:\Users\WDAGUtilityAccount\Desktop\PBStudioRelease\tests\qa_artifacts\otk021_backup_restore_portable_result.json

## Honest Limit

This proof runs the real PB Studio Python services inside Windows Sandbox using
the mapped PB Studio Python environment as runtime. It proves VM execution of
the service roundtrips, not manual GUI clicks inside the installed app and not
public distribution upload.
