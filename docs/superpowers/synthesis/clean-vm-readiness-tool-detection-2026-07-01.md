---
status: blocked
plan: PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09
task: OTK-021 90 Live-Verify
date: 2026-07-01
---

# Clean-VM Readiness Tool Detection

Scope: improve clean-VM readiness evidence by detecting VM control tools more
accurately.

Updated verifier: `scripts/diag/verify_clean_vm_readiness.py`.

Output artifact: `tests/qa_artifacts/clean_vm_readiness.json`.

Changes:

- `Get-VM` is detected as a PowerShell command, not as an executable on PATH.
- `vmrun` and `VBoxManage` still use PATH lookup and known install paths.
- Result includes candidate details for each VM tool.

Honest limit: this preflight still does not run a clean Windows VM, install PB
Studio, or create `release_gate_proof` frontmatter. `VM-001` remains open until
a real clean-VM install proof exists.
