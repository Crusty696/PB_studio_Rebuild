# Clean VM Readiness Preflight 2026-07-01

Status: `clean-vm-not-ready-release-blocked`

## Scope

This preflight checks whether the current machine can run an automated clean VM
installer test for PB Studio.

It does not run a VM, does not install PB Studio, and does not clear `VM-001`.

## Command

```powershell
& "C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe" -m py_compile scripts\diag\verify_clean_vm_readiness.py
& "C:\Users\David_Lochmann\miniconda3\envs\pb-studio\python.exe" scripts\diag\verify_clean_vm_readiness.py
```

## Result

- `py_compile`: Exit 0.
- `scripts/diag/verify_clean_vm_readiness.py`: Exit 0.
- JSON artifact: `tests/qa_artifacts/clean_vm_readiness.json`.
- `clean_vm_ready`: `false`.

## Evidence

Current process:

- Admin: `false`

VM control tools:

- `Get-VM`: missing
- `vmrun`: missing
- `VBoxManage`: missing

Hyper-V checks:

- `Get-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V-All` failed:
  elevated rights required.
- `Get-VM` command missing.

Release artifacts:

- Installer stub exists:
  `dist/pb_studio_setup_v0.5.0.exe`
- Installer stub size:
  `422,926` bytes
- NSISBI payload exists:
  `dist/pb_studio_setup_v0.5.0.nsisbin`
- NSISBI payload size:
  `2,815,066,504` bytes

Blockers:

- `not-running-as-admin`
- `no-vm-control-tool-found`

## Verdict

`VM-001` remains valid. A clean Windows VM install test cannot be automated from
this current process/state.

Required before clearing `VM-001`:

- run from an admin-capable environment or configured VM runner
- provide a controllable clean Windows 11 VM without development Python
- provide/install NVIDIA driver path appropriate for the GTX 1060 target
- copy installer stub and `.nsisbin` payload together
- run the installer in that VM
- produce a schema-valid synthesis with:
  - `release_gate_proof: true`
  - `proof_type: clean-vm-install`
  - `status: pass`
  - `evidence_level: live`

No release-ready marker may be set from this preflight.
