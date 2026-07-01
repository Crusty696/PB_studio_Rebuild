---
status: blocked
plan: PB-STUDIO-OFFENE-TASKS-KONSOLIDIERUNG-MASTERPLAN-2026-06-09
task: OTK-021 90 Live-Verify
date: 2026-07-01
---

# Release Cutover Manifest

Scope: generate a machine-readable cutover manifest for the current release blockers.

Added verifier: `scripts/diag/verify_release_cutover_manifest.py`.

Output artifact: `tests/qa_artifacts/release_cutover_manifest.json`.

Expected current result:

- `status=blocked`.
- `release_ready=false`.
- Open blockers include `DG-001`, `SIGN-001`, `VM-001`, `GUI-001`.
- `required_actions` lists the exact proof work for each blocker.
- `final_gate_command` remains `tools\release_gate.py`.

Honest limit: this manifest does not sign the installer, run a clean VM,
launch the installed app, resolve DG-001, or create a release. It only records
the current blocker-to-proof map.
